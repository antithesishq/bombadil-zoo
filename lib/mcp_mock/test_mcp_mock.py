"""Contract tests for the shared MCP stdio fixture server."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class McpMockTest(unittest.TestCase):
    def test_stdio_lifecycle_catalog_and_results(self):
        config = {
            "name": "fixture-mcp",
            "tools": [
                {"name": "echo", "description": "Echo fixture text",
                 "inputSchema": {"type": "object"},
                 "text": "prefix ", "echo_argument": "text"},
                {"name": "unicode", "description": "Unicode result",
                 "inputSchema": {"type": "object"}, "text": "中文\n", "repeat": 2},
                {"name": "fail", "description": "Expected failure",
                 "inputSchema": {"type": "object"}, "text": "failure", "isError": True},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps(config))
            proc = subprocess.Popen(
                [sys.executable, "-m", "mcp_mock", str(path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            )
            self.addCleanup(proc.kill)
            ident = 0

            def call(method, params=None):
                nonlocal ident
                ident += 1
                proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": ident,
                                             "method": method, "params": params or {}}) + "\n")
                proc.stdin.flush()
                return json.loads(proc.stdout.readline())

            initialized = call("initialize", {"protocolVersion": "2025-03-26"})
            self.assertEqual(initialized["result"]["serverInfo"]["name"], "fixture-mcp")
            catalog = call("tools/list")["result"]["tools"]
            self.assertEqual([tool["name"] for tool in catalog], ["echo", "unicode", "fail"])
            self.assertNotIn("text", catalog[0])
            echoed = call("tools/call", {"name": "echo", "arguments": {"text": "blåbær 中文"}})
            self.assertEqual(echoed["result"]["content"][0]["text"], "prefix blåbær 中文")
            repeated = call("tools/call", {"name": "unicode", "arguments": {}})
            self.assertEqual(repeated["result"]["content"][0]["text"], "中文\n中文\n")
            failed = call("tools/call", {"name": "fail", "arguments": {}})
            self.assertTrue(failed["result"]["isError"])
            unknown = call("tools/call", {"name": "missing", "arguments": {}})
            self.assertTrue(unknown["result"]["isError"])
            self.assertEqual(call("ping")["result"], {})
            missing = call("unknown/method")
            self.assertEqual(missing["error"]["code"], -32601)
            proc.stdin.close()
            self.assertEqual(proc.wait(timeout=5), 0)
            proc.stdout.close()


if __name__ == "__main__":
    unittest.main()
