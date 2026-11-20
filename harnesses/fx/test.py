"""Exercise fixture tool calls and real fx approval UI in disposable homes."""

import base64
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
import urllib.request
from mock import provider

FX = sys.argv.pop(1)


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "project"
        (self.project / "src").mkdir(parents=True)
        (self.project / "src/hello.py").write_text('print("hello")\n')
        (self.project / "pixel.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        ))
        skill = self.project / ".agents/skills/zoo-review"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: zoo-review\ndescription: Fixture review\n---\nZOO_FIXTURE_SKILL\n"
        )
        self.env = {**os.environ, "HOME": str(self.home), "TERM": "xterm-256color",
                    "FX_AUTO_UPGRADE": "0", "FX_SOUND": "0", "FX_NO_OPEN_BROWSER": "1"}
        self.server = self.enterContext(provider(self.home))

    def ask(self, scenario, *args):
        result = subprocess.run(
            [FX, "ask", "--json", "--full-access",
             *args, f"zoo:tool-{scenario}"], cwd=self.project, env=self.env,
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reply = json.loads(result.stdout)
        self.assertTrue(reply["output"].startswith(f"ZOO_TOOL_DONE {scenario}\n"), reply)
        results = json.loads(reply["output"].split("\n", 1)[1])
        self.assertTrue(results, reply)
        return reply, results

    def test_chain_and_resumed_turn(self):
        reply, results = self.ask("chain")
        self.assertEqual(len(results), 3)
        self.assertEqual((self.project / "zoo-result.txt").read_text(), "ZOO_WRITTEN\n")
        self.assertIn("ZOO_WRITTEN", str(results[1]))
        self.assertEqual((self.project / "src/hello.py").read_text(), 'print("ZOO_EDITED 中文")\n')
        # Old tool messages must not suppress the next turn's fixture.
        _, results = self.ask("read", "--resume", reply["session_id"])
        self.assertEqual(len(results), 1)
        self.assertIn("ZOO_EDITED", str(results))

    def test_batch_and_error_results(self):
        _, results = self.ask("batch")
        self.assertEqual(len(results), 2)
        self.assertIn("hello", str(results))
        self.assertIn("ZOO_SHELL_OK", str(results))
        for scenario, marker in [("slow", "ZOO_SLOW_OK"), ("fail", "ZOO_EXPECTED_FAILURE"),
                                 ("missing", "path not found"), ("bad-args", "must be a string"),
                                 ("unknown", "unsupported tool")]:
            with self.subTest(scenario=scenario):
                _, results = self.ask(scenario)
                self.assertEqual(len(results), 1)
                self.assertIn(marker.lower(), str(results).lower())

    def test_source_boundary_tools(self):
        _, results = self.ask("interleaved")
        self.assertEqual(len(results), 2)
        self.assertIn("hello", str(results))
        self.assertIn("ZOO_SHELL_OK", str(results))
        for scenario in ("read-offset", "read-max"):
            with self.subTest(scenario=scenario):
                _, results = self.ask(scenario)
                self.assertIn("beyond end of file", str(results))
        _, results = self.ask("grep")
        self.assertIn("hello", str(results))
        _, results = self.ask("grep-max")
        self.assertIn("no matches", str(results))
        _, results = self.ask("glob")
        self.assertIn("hello.py", str(results))
        _, results = self.ask("skill")
        self.assertIn("ZOO_FIXTURE_SKILL", str(results))
        _, results = self.ask("question-invalid")
        self.assertIn("only available in the interactive shell", str(results))

    def test_mcp_and_shell_session_tools(self):
        _, results = self.ask("mcp")
        self.assertIn("ZOO_MCP_ECHO zoo", str(results))
        _, results = self.ask("mcp-search")
        self.assertEqual(len(results), 2)
        self.assertIn("ZOO_MCP_ECHO zoo-search", str(results))
        _, results = self.ask("mcp-fail")
        self.assertIn("ZOO_MCP_EXPECTED_FAILURE", str(results))
        _, results = self.ask("shell-interactive")
        self.assertEqual(len(results), 2)
        self.assertIn("ZOO_SHELL_INPUT:zoo", str(results))
        _, results = self.ask("shell-stop")
        self.assertEqual(len(results), 3)
        self.assertIn("stop", str(results).lower())
        _, results = self.ask("read-result-missing")
        self.assertIn("ResultHandleNotFound", str(results))

    def test_reasoning_and_fragmented_sse(self):
        for fixture in ("reasoning", "sse-split", "usage", "usage-trailer", "usage-huge"):
            with self.subTest(fixture=fixture):
                result = subprocess.run(
                    [FX, "ask", "--json", "--full-access", f"zoo:{fixture}"],
                    cwd=self.project, env=self.env, capture_output=True, text=True, timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("ZOO_MOCK_OK", json.loads(result.stdout)["output"])

    def test_image_attachment_reaches_provider(self):
        result = subprocess.run(
            [FX, "ask", "--json", "--full-access", "--image", "pixel.png", "zoo:vision"],
            cwd=self.project, env=self.env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        request = self.server.requests[-1]
        users = [message for message in request["messages"] if message.get("role") == "user"]
        content = users[-1]["content"]
        self.assertIsInstance(content, list)
        self.assertIn("zoo:vision", content[0]["text"])
        images = [part for part in content if part.get("type") == "image_url"]
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_permission_review_with_null_content(self):
        settings = json.loads((self.home / ".fx/settings.json").read_text())
        base_url = settings["providers"]["local"]["base_url"]
        payload = json.dumps({
            "messages": [
                {"role": "system", "content": "<permission_review>\naction: write_file\narguments_json: {}\n"},
                {"role": "assistant", "content": None},
            ],
            "tools": [{"type": "function", "function": {"name": "permission_decision"}}],
        }).encode()
        request = urllib.request.Request(
            base_url + "/chat/completions", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode()
        self.assertIn('"name": "p"', body)
        self.assertIn('"name": "ermission_decision"', body)
        self.assertIn('\\"decision\\": \\"caution\\"', body)

    def assert_user_action_shows(self, command, marker, setup=None, preserve_input=False):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 100, 0, 0))
        proc = subprocess.Popen(
            [FX, "--ask"], cwd=self.project, env=self.env,
            stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
        )
        os.close(slave)
        captured = bytearray()

        def wait_for(text):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    data = os.read(master, 65536)
                    captured.extend(data)
                    if b"\x1b[6n" in data:
                        os.write(master, b"\x1b[1;1R")
                plain = re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", bytes(captured))
                if text.encode() in plain:
                    return
            self.fail(f"Missing {text!r}: {captured[-6000:]!r}")

        try:
            wait_for("Run /help for commands")
            if setup is not None:
                os.write(master, b"\x15" + setup[0].encode() + b"\r")
                wait_for(setup[1])
            captured.clear()
            os.write(master, (b"" if preserve_input else b"\x15") + command.encode() + b"\r")
            wait_for(marker)
            self.assertIsNone(proc.poll())
        finally:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=5)
            os.close(master)

    def test_user_reachable_menu_screens(self):
        # Markers come from tui-performance.test.ts, except usage, which is
        # the local provider's actual notice rather than the AI Gateway label.
        screens = [
            ("/help", "Commands "), ("/settings", "Settings"),
            ("/model", "Models "), ("/resume", "Sessions "),
            ("/mcp", "ready, 3 tools"), ("/usage", "usage: this provider's usage isn't shown yet"),
            ("/statusline", "Status line"), ("/workspace", "enter use"),
            ("/permissions", "Permissions"), ("/effort", "Effort"),
            ("/skills", "Skills"), ("/agents", "Agents"),
        ]
        for command, marker in screens:
            with self.subTest(command=command):
                self.assert_user_action_shows(command, marker)
        with self.subTest(command="/fork"):
            self.assert_user_action_shows("/fork", "enter fork", ("zoo:markdown", "ZOO_MOCK_OK"))
        with self.subTest(command="/images"):
            self.assert_user_action_shows("/images", "pixel.png", ("/image pixel.png", "attached image: pixel.png"), True)
        with self.subTest(command="ctrl+p"):
            self.assert_user_action_shows("\x10", "/model zoo-mock", preserve_input=True)

    def test_question_validation(self):
        cases = [
            ("question-overflow", "provide 1 to 20 questions"),
            ("question-options", "provide 2 to 6 options"),
            ("question-duplicate", "label repeats an earlier"),
        ]
        for scenario, marker in cases:
            with self.subTest(scenario=scenario):
                self.assert_user_action_shows(f"zoo:tool-{scenario}", marker)

    def test_approval_and_denial_after_resize(self):
        for mode, choice, approved in [("--ask", "1", True), ("--ask", "3", False),
                                       ("--auto", "", True)]:
            with self.subTest(mode=mode, choice=choice):
                target = self.project / "zoo-result.txt"
                target.write_text("ORIGINAL\n")
                master, slave = pty.openpty()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 100, 0, 0))
                proc = subprocess.Popen(
                    [FX, mode, "zoo:tool-write"],
                    cwd=self.project, env=self.env, stdin=slave, stdout=slave,
                    stderr=slave, start_new_session=True,
                )
                os.close(slave)
                captured = bytearray()

                def wait_for(text):
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        if select.select([master], [], [], 0.1)[0]:
                            data = os.read(master, 65536)
                            captured.extend(data)
                            if b"\x1b[6n" in data:
                                os.write(master, b"\x1b[1;1R")
                        plain = re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", bytes(captured))
                        if text.encode() in plain:
                            return
                    self.fail(f"Missing {text!r}: {captured[-6000:]!r}")

                try:
                    if mode == "--ask":
                        wait_for("Apply this change?")
                        self.assertEqual(target.read_text(), "ORIGINAL\n")
                        captured.clear()
                        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 18, 72, 0, 0))
                        os.killpg(proc.pid, signal.SIGWINCH)
                        wait_for("Apply this change?")
                        captured.clear()
                        os.write(master, choice.encode())
                    wait_for("ZOO_TOOL_DONE write")
                    if mode == "--auto":
                        self.assertNotIn(b"Apply this change?", captured)
                    self.assertEqual(target.read_text(), "ZOO_WRITTEN\n" if approved else "ORIGINAL\n")
                finally:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=5)
                    os.close(master)


if __name__ == "__main__":
    unittest.main()
