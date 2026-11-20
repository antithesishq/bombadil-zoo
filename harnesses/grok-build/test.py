"""Check the fixture protocol and the wrapper's exit-status contract."""

from http.client import HTTPConnection
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from threading import Thread
import unittest
from http.server import ThreadingHTTPServer

from mock import CHAIN, FIXTURES, Handler, MARKDOWN, SCENARIOS, TOOLS


class MockTests(unittest.TestCase):
    def test_responses(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for scenario in ("markdown", "slow", "rate-limit", "server-error", "malformed",
                             "disconnect", "reasoning", "tool-call"):
                with self.subTest(scenario=scenario):
                    conn = HTTPConnection(*server.server_address, timeout=5)
                    conn.request("POST", "/v1/chat/completions", json.dumps({
                        "model": "zoo-mock", "stream": True,
                        "messages": [{"role": "user", "content": f"zoo:{scenario}"}],
                    }), {"Content-Type": "application/json"})
                    response = conn.getresponse()
                    body = response.read().decode()
                    conn.close()
                    if scenario in ("rate-limit", "server-error"):
                        self.assertEqual(response.status, 429 if scenario == "rate-limit" else 500)
                        self.assertIn(f"ZOO_MOCK_{scenario}", json.loads(body)["error"]["message"])
                    else:
                        self.assertEqual(response.status, 200)
                        data = [line[6:] for line in body.splitlines() if line.startswith("data: ")]
                        if scenario == "malformed":
                            with self.assertRaises(json.JSONDecodeError):
                                json.loads(data[0])
                        else:
                            chunks = [json.loads(d)["choices"][0] for d in data if d != "[DONE]"]
                            text = "".join(c["delta"].get("content") or "" for c in chunks)
                            if scenario == "reasoning":
                                reasoning = "".join(c["delta"].get("reasoning_content", "")
                                                    for c in chunks)
                                self.assertIn("ZOO_MOCK_REASONING", reasoning)
                                self.assertIn("More thought", reasoning)
                            if scenario == "tool-call":
                                calls = [call for c in chunks
                                         for call in c["delta"].get("tool_calls", [])]
                                self.assertEqual(calls[0]["id"], "call_zoo_0_0")
                                self.assertEqual(calls[0]["function"]["name"], "run_terminal_command")
                                arguments = "".join(call["function"].get("arguments", "")
                                                    for call in calls)
                                self.assertEqual(json.loads(arguments)["command"],
                                                 "printf ZOO_MOCK_TOOL_DONE")
                                self.assertEqual(chunks[-1]["finish_reason"], "tool_calls")
                                self.assertEqual(data[-1], "[DONE]")

                                follow_up = HTTPConnection(*server.server_address, timeout=5)
                                follow_up.request("POST", "/v1/chat/completions", json.dumps({
                                    "model": "zoo-mock", "stream": True,
                                    "messages": [
                                        {"role": "user", "content": "zoo:tool-call"},
                                        {"role": "tool", "content": "ZOO_MOCK_TOOL_DONE"},
                                    ],
                                }), {"Content-Type": "application/json"})
                                final_body = follow_up.getresponse().read().decode()
                                follow_up.close()
                                self.assertIn("ZOO_MOCK_OK", final_body)
                                self.assertNotIn("tool_calls", final_body)
                            elif scenario == "disconnect":
                                self.assertEqual(text, "ZOO_MOCK_PARTIAL")
                                self.assertNotIn("[DONE]", data)
                                self.assertTrue(all(c["finish_reason"] is None for c in chunks))
                            elif scenario != "tool-call":
                                self.assertEqual(text, MARKDOWN)
                                self.assertEqual(chunks[-1]["finish_reason"], "stop")
                                self.assertEqual(data[-1], "[DONE]")
        finally:
            server.shutdown()
            server.server_close()

    def test_every_scenario_answers(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario):
                    conn = HTTPConnection(*server.server_address, timeout=20)
                    conn.request("POST", "/v1/chat/completions", json.dumps({
                        "model": "zoo-mock", "stream": True,
                        "messages": [{"role": "user", "content": f"zoo:{scenario}"}],
                    }), {"Content-Type": "application/json"})
                    response = conn.getresponse()
                    body = response.read().decode()
                    conn.close()
                    data = [line[6:] for line in body.split("\n") if line.startswith("data: ")]
                    if scenario in TOOLS:
                        chunks = [json.loads(d)["choices"][0] for d in data if d != "[DONE]"]
                        names = [call["function"]["name"] for c in chunks
                                 for call in c["delta"].get("tool_calls", [])
                                 if "name" in call["function"]]
                        self.assertEqual(names, [name for name, _ in TOOLS[scenario]])
                    elif scenario in FIXTURES:
                        chunks = [json.loads(d)["choices"][0] for d in data if d != "[DONE]"]
                        text = "".join(c["delta"].get("content") or "" for c in chunks)
                        self.assertEqual(text, FIXTURES[scenario])
        finally:
            server.shutdown()
            server.server_close()

    def test_chain_runs_for_a_fixed_number_of_rounds(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            messages = [{"role": "user", "content": "zoo:chain"}]
            names = []
            for _ in range(len(CHAIN) + 3):
                conn = HTTPConnection(*server.server_address, timeout=20)
                conn.request("POST", "/v1/chat/completions", json.dumps({
                    "model": "zoo-mock", "stream": True, "messages": messages,
                }), {"Content-Type": "application/json"})
                body = conn.getresponse().read().decode()
                conn.close()
                chunks = [json.loads(line[6:])["choices"][0] for line in body.split("\n")
                          if line.startswith("data: ") and line != "data: [DONE]"]
                called = [c["function"]["name"] for chunk in chunks
                          for c in chunk["delta"].get("tool_calls", [])
                          if "name" in c["function"]]
                if not called:
                    break
                names += called
                messages += [{"role": "assistant", "content": None},
                             {"role": "tool", "content": "ok"}]
            self.assertEqual(names, [name for name, _ in CHAIN])
        finally:
            server.shutdown()
            server.server_close()

    def run_wrapper(self, code):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("mock.py")), sys.executable, "-c", code],
            env=os.environ | {"HOME": temp.name}, cwd=temp.name,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(lambda: process.poll() is None and process.kill())
        return process

    def test_wrapper_survives_interrupt(self):
        process = self.run_wrapper('import time; print("ready", flush=True); time.sleep(0.2)')
        self.assertEqual(process.stdout.readline().strip(), "ready")
        process.send_signal(signal.SIGINT)
        _, error = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, error)

    def test_target_signal_is_preserved(self):
        process = self.run_wrapper('import os, signal; os.kill(os.getpid(), signal.SIGTERM)')
        process.communicate(timeout=5)
        self.assertEqual(process.returncode, -signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
