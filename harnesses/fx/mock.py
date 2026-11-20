"""Private OpenAI-compatible fixture provider; never uses real credentials."""

from contextlib import contextmanager
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import time
import zlib


# Fixture names the handler recognizes after "zoo:". Tools are longest first,
# so a name is never read as a prefix of a longer one.
REPLIES = ("markdown", "error", "html-error", "malformed", "truncated", "sse-split",
           "reasoning", "long", "markdown-edge", "ansi", "empty", "slow", "usage",
           "usage-huge", "usage-trailer")
TOOLS = tuple(sorted((
    "shell-interactive", "shell-stop", "read-offset", "read-max", "read-result-missing",
    "read", "write", "edit", "shell", "slow", "fail", "missing", "bad-args", "unknown",
    "batch", "interleaved", "sparse", "chain", "diff", "grep-max", "grep", "glob",
    "mcp-search", "mcp-fail", "mcp", "skill", "question-overflow", "question-options",
    "question-duplicate", "question-invalid", "question-batch", "question-many",
    "question-tall", "question"), key=len, reverse=True))
SCENARIOS = (*REPLIES, *(f"tool-{name}" for name in TOOLS))


def with_fixture(prompt, tools):
    """Give a prompt without a marker a fixture chosen by its hash, so that
    generated text reaches every fixture and the same prompt always gets
    the same one. Tool calls go only to requests that offer tools."""
    if "zoo:" in prompt:
        return prompt
    names = SCENARIOS if tools else REPLIES
    return f"{prompt} zoo:{names[zlib.crc32(prompt.encode()) % len(names)]}"


def tool_plan(scenario):
    """Fixed operations only: prompt text never becomes a path or command."""
    def shell(command, yield_time_ms=None):
        # fx resolves the login shell from passwd, not SHELL. Nix has no
        # /bin/bash, so select the harness-provided executable explicitly.
        request = {"action": "run", "command": command, "tty": True,
                   "shell": {"kind": "executable", "clean_start": True,
                              "path": os.environ["SHELL"]}}
        if yield_time_ms is not None:
            request["yield_time_ms"] = yield_time_ms
        return ("shell", {"request": request})

    def ask(questions):
        return ("ask_user_question", {"questions": questions})

    read = ("read_file", {"path": "src/hello.py"})
    write = ("write_file", {"path": "zoo-result.txt", "content": "ZOO_WRITTEN\n"})
    edit = ("edit_file", {"path": "src/hello.py", "old_string": 'print("hello")',
                          "new_string": 'print("ZOO_EDITED 中文")'})
    command = shell("printf ZOO_SHELL_OK")
    choices = [{"label": "Apply", "description": "Make the change."},
               {"label": "Cancel", "description": "Leave it unchanged."}]
    tall_choices = [
        {"label": f"Option {i}", "description":
         f"Steps for option {i}:\n- run `check {i}`\n- see [docs](https://example.invalid/{i})\n"
         f"**blåbær 中文 👩‍💻** {'wide ' * 12}"}
        for i in range(1, 7)
    ]
    return {
        "read": [[read]], "write": [[write]], "edit": [[edit]], "shell": [[command]],
        "slow": [[shell("sleep 1; printf ZOO_SLOW_OK")]],
        "fail": [[shell("printf ZOO_EXPECTED_FAILURE >&2; exit 7")]],
        "missing": [[("read_file", {"path": "zoo-missing.txt"})]],
        "bad-args": [[("read_file", {"path": 42})]],
        "unknown": [[("zoo_unknown_tool", {})]],
        "batch": [[read, command]],
        "interleaved": [[read, command]],
        # A sparse index leaves holes without IDs in the reducer's tool array.
        "sparse": [[read]],
        "chain": [[write], [("read_file", {"path": "zoo-result.txt"})], [edit]],
        "diff": [[("write_file", {"path": "zoo-diff.txt", "content": "".join(
            f"line {i:03}: blåbær 中文 👩‍💻 {'wide ' * 15}\n" for i in range(80))})]],
        "read-offset": [[("read_file", {"path": "src/hello.py", "start_line": 2,
                                        "line_count": 1})]],
        "read-max": [[("read_file", {"path": "src/hello.py",
                                     "start_line": 2**63 - 1, "line_count": 2000})]],
        "grep": [[("grep_files", {"pattern": "hello", "path": ".", "head_limit": 100,
                                  "offset": 0, "context_lines": 5})]],
        "grep-max": [[("grep_files", {"pattern": "hello", "path": ".", "head_limit": 100,
                                      "offset": 2**63 - 1, "context_lines": 5})]],
        "glob": [[("glob_files", {"pattern": "**/*", "path": "."})]],
        "mcp": [[("toolbox", {"run": "mcp_zoo_echo", "arguments": {"text": "zoo"}})]],
        "mcp-search": [[("toolbox", {"search": "echo text", "server": "zoo"})],
                       [("toolbox", {"run": "mcp_zoo_echo", "arguments": {"text": "zoo-search"}})]],
        "mcp-fail": [[("toolbox", {"run": "mcp_zoo_fail", "arguments": {}})]],
        "shell-interactive": [
            [shell("printf 'ZOO_SHELL_READY\\n'; read -r line; printf 'ZOO_SHELL_INPUT:%s\\n' \"$line\"", 0)],
            [("shell", {"request": {"action": "interact", "session_id": "dynamic",
                                    "chars": "zoo\n", "yield_time_ms": 1000}})],
        ],
        "shell-stop": [[shell("printf 'ZOO_SHELL_READY\\n'; sleep 30", 0)],
                       [("shell", {"request": {"action": "interact", "session_id": "dynamic",
                                               "chars": "", "yield_time_ms": 1000}})],
                       [("shell", {"request": {"action": "stop", "session_id": "dynamic",
                                               "force": True}})]],
        "read-result-missing": [[("read_tool_result", {
            "handle": "unknown-dogfood-handle", "start_byte": 1, "byte_count": 64})]],
        "skill": [[("toolbox", {"open": "zoo-review", "kind": "skill",
                                "resource": "SKILL.md", "offset": 0})]],
        "question": [[ask([{"question": "Apply the fixture change?", "options": choices}])]],
        "question-invalid": [[ask([])]],
        "question-batch": [[ask([
            {"question": f"Question {i} of four?", "options": choices} for i in range(1, 5)
        ])]],
        "question-many": [[ask([
            {"question": f"Boundary question {i} of twenty?", "options": choices} for i in range(1, 21)
        ])]],
        "question-overflow": [[ask([
            {"question": f"Overflow question {i}?", "options": choices} for i in range(1, 22)
        ])]],
        "question-options": [[ask([{
            "question": "Too many options?",
            "options": [{"label": f"Option {i}"} for i in range(1, 8)],
        }])]],
        "question-duplicate": [[ask([{
            "question": "Duplicate labels?",
            "options": [{"label": "Yes"}, {"label": " yes "}],
        }])]],
        "question-tall": [[ask([{
            "question": "# Deployment\n\nChoose **one** option.\n\n| Risk | Mitigation |\n|---|---|\n| data loss | backup |\n\n"
                        "See [the runbook](https://example.invalid/runbook) before answering.",
            "options": tall_choices,
        }])]],
    }[scenario]


def message_text(message):
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content
                         if isinstance(part, dict) and part.get("type") == "text")
    return ""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"data": [{"id": "zoo-mock", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(request)
        messages = request.get("messages", [])
        user_index = next((i for i in range(len(messages) - 1, -1, -1)
                           if messages[i].get("role") == "user"), -1)
        prompt = message_text(messages[user_index]) if user_index >= 0 else ""
        prompt = with_fixture(prompt, bool(request.get("tools")))
        fixture = re.search(r"zoo:([a-z][a-z0-9-]*)", prompt)
        fixture = fixture[1] if fixture else ""
        fixture_count = self.server.fixture_counts.get(fixture, 0)
        self.server.fixture_counts[fixture] = fixture_count + 1
        # Only results from this user turn advance the plan. Earlier calls must
        # not suppress fixtures in subsequent turns or resumed conversations.
        results = [m for m in messages[user_index + 1:] if m.get("role") == "tool"]
        scenario = re.search(
            rf"zoo:tool-({'|'.join(TOOLS)})\b",
            prompt,
        )
        calls = None
        step = 0
        if any(t.get("function", {}).get("name") == "permission_decision"
               for t in request.get("tools", [])):
            # For actions sent to the auto reviewer, request a user decision.
            # fx can still allow ordinary workspace writes without review.
            texts = [message_text(message) for message in messages]
            instruction = next(text for text in texts if "<permission_review>" in text)
            action = instruction[instruction.rfind("\naction: "):]
            evidence = re.search(r"\n(?:command|arguments_json|path): ([^\n]+)", action)[1]
            calls = [("permission_decision", {"decision": "caution", "category": "system_harm",
                                              "evidence": html.unescape(evidence)[:160]})]
        elif scenario:
            plan = tool_plan(scenario[1])
            completed = {m.get("tool_call_id") for m in results}
            for step, batch in enumerate(plan):
                if not all(f"zoo-{user_index}-{step}-{i}" in completed for i in range(len(batch))):
                    calls = batch
                    break
            if calls is not None and step >= 1 and scenario[1] in ("shell-interactive", "shell-stop"):
                content = results[-1].get("content", "")
                session_id = re.search(r'"session_id":\s*"([^"]+)"', content)
                if session_id is None:
                    raise ValueError(f"Missing shell session ID in {content!r}")
                calls[0][1]["request"]["session_id"] = session_id[1]
        if calls is not None:
            self.start_sse()
            try:
                if scenario and scenario[1] == "sparse":
                    # Index zero and one stay empty, so finish validates their IDs.
                    self.event({"tool_calls": [{"index": 2, "id": "zoo-sparse",
                                "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]})
                else:
                    encoded = [json.dumps(args, ensure_ascii=False) for _, args in calls]
                    # Split names as well as arguments. Interleaved calls share
                    # each argument chunk boundary instead of arriving serially.
                    for i, (name, _) in enumerate(calls):
                        self.event({"tool_calls": [{"index": i, "id": f"zoo-{user_index}-{step}-{i}",
                                    "type": "function", "function": {"name": name[:1], "arguments": ""}}]})
                    if scenario and scenario[1] == "interleaved":
                        for i, (name, _) in enumerate(calls):
                            self.event({"tool_calls": [{"index": i, "function": {"name": name[1:]}}]})
                        for offset in range(0, max(map(len, encoded)), 64):
                            for i, arguments in enumerate(encoded):
                                self.event({"tool_calls": [{"index": i, "function": {
                                    "arguments": arguments[offset:offset + 64]}}]})
                    else:
                        for i, ((name, _), arguments) in enumerate(zip(calls, encoded)):
                            self.event({"tool_calls": [{"index": i, "function": {"name": name[1:]}}]})
                            for offset in range(0, len(arguments), 64):
                                self.event({"tool_calls": [{"index": i, "function": {
                                    "arguments": arguments[offset:offset + 64]}}]})
                self.event({}, "tool_calls")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        if fixture == "error":
            try:
                self.send_error(429, "Fixture rate limit")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if fixture == "html-error":
            body = b"<html><body>fixture upstream failure</body></html>"
            self.send_response(503)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if fixture in ("malformed", "truncated") and fixture_count == 0:
            self.start_sse()
            if fixture == "malformed":
                self.wfile.write(b"data: {not-json}\n\n")
            else:
                self.event({"content": "unfinished fixture"})
            self.close_connection = True
            return
        if fixture == "sse-split":
            self.start_sse()
            chunks = [
                {"choices": [{"index": 0, "delta": {"content": "ZOO_MOCK_OK split\r\n"}, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]
            wire = "\ufeff: fixture comment\r\n" + "".join(
                f"data: {json.dumps(chunk)}\r\n\r\n" for chunk in chunks
            ) + "data: [DONE]\r\n\r\n"
            try:
                for offset in range(0, len(wire.encode()), 3):
                    self.wfile.write(wire.encode()[offset:offset + 3])
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if fixture == "reasoning":
            self.start_sse()
            try:
                self.event({
                    "reasoning": "Think **deeply**.\n",
                    "reasoning_content": "检查 👩‍💻",
                    "reasoning_details": [{"type": "reasoning.text", "text": "detail", "signature": "opaque"}],
                })
                self.event({"content": "ZOO_MOCK_OK reasoning\n\n> nested **answer**\n"},
                           usage={"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5})
                self.event({}, "stop")
                self.raw_event({"choices": [], "usage": {
                    "prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11,
                    "prompt_tokens_details": {"cached_tokens": 2},
                    "completion_tokens_details": {"reasoning_tokens": 1},
                }})
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        text = "ZOO_MOCK_OK\n\n# Fixture\n\n- hello\n- blåbær 中文 👩‍💻\n\n```python\nprint('hello')\n```\n"
        if scenario:
            text = f"ZOO_TOOL_DONE {scenario[1]}\n" + json.dumps(results, ensure_ascii=False)
        if fixture == "long":
            text += "| Column | Value |\n|---|---|\n" + "| 中文 | café 👩‍💻 |\n" * 100
        if fixture == "markdown-edge":
            text += (
                "\n\n> ## Nested [link](https://example.invalid/a_(b))\n"
                "> - [x] **completed**\n> 2. second with `code`\n\n"
                "Term\n: definition with ![image alt](https://example.invalid/image.png)\n"
                "Footnote[^1] and ~~strike~~ and __strong__.\n\n[^1]: footnote body\n\n"
                "| Left | Center | Right | Extra |\n|:---|:---:|---:|---|\n"
                "| á̂̃ | **b** | `c` |\n| 👩‍💻 | [link](https://example.invalid) | z | extra |\n\n"
                "~~~~python\nunclosed **fence** with \x1b[2J control\n"
            )
        if fixture == "ansi":
            text += "\n\nClear \x1b[2J and \x1b]0;title\x07 remain visible text.\n"
        if fixture == "empty" and fixture_count == 0:
            text = ""
        self.start_sse()
        try:
            for offset in range(0, len(text), 24):
                self.event({"content": text[offset:offset + 24]})
                if fixture == "slow":
                    time.sleep(0.05)
            usage = None
            if fixture == "usage":
                usage = {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11,
                         "prompt_tokens_details": {"cached_tokens": 2},
                         "completion_tokens_details": {"reasoning_tokens": 1}}
            if fixture == "usage-huge":
                usage = {"prompt_tokens": 2**63 - 2, "completion_tokens": 1,
                         "total_tokens": 2**63 - 1}
            self.event({}, "stop", usage=usage)
            if fixture == "usage-trailer":
                self.raw_event({"choices": [], "usage": {
                    "prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11,
                }})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # Cancellation is an expected fuzz action.

    def start_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

    def raw_event(self, payload):
        self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
        self.wfile.flush()

    def event(self, delta, finish=None, usage=None):
        chunk = {"id": "zoo", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
        if usage is not None:
            chunk["usage"] = usage
        self.raw_event(chunk)


@contextmanager
def provider(home):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    server.fixture_counts = {}
    config = home / ".fx"
    config.mkdir(parents=True, exist_ok=True)
    (config / "zoo-mcp.json").write_text(json.dumps({
        "name": "zoo-mcp",
        "tools": [
            {"name": "echo", "description": "Return fixture text",
             "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
             "text": "ZOO_MCP_ECHO ", "echo_argument": "text"},
            {"name": "unicode", "description": "Return Unicode and a wide table",
             "inputSchema": {"type": "object", "properties": {}},
             "text": "blåbær 中文 👩‍💻\n" + "| A | B |\n|---|---|\n| 中文 | café |\n" * 30},
            {"name": "fail", "description": "Return an expected tool failure",
             "inputSchema": {"type": "object", "properties": {}},
             "text": "ZOO_MCP_EXPECTED_FAILURE", "isError": True},
        ],
    }))
    (config / "mcp.json").write_text(json.dumps({
        "mcp": {"zoo": {"command": [sys.executable, "-m", "mcp_mock",
                                      str(config / "zoo-mcp.json")],
                        "environment": {"PYTHONPATH": os.environ["PYTHONPATH"]}}},
    }))
    (config / "settings.json").write_text(json.dumps({
        "provider": "local", "auto_upgrade": False, "permission_mode": "ask",
        "providers": {"local": {
            "protocol": "openai-chat-completions",
            "reviewer_model": "zoo-mock",
            "base_url": f"http://127.0.0.1:{server.server_port}/v1",
            "auth": {"type": "none"},
            "model_metadata": {"zoo-mock": {"context_window": 262144,
                                           "max_output_tokens": 8192,
                                           "supports_tool_use": True,
                                           "supports_vision": True,
                                           "reasoning_efforts": {
                                               "low": {"reasoning_effort": "low"},
                                               "high": {"reasoning_effort": "high"},
                                           }}},
        }},
        "models": {"local": "zoo-mock"},
    }))
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def main():
    with provider(Path.home()):
        result = subprocess.run(sys.argv[1:])
    # Preserve fatal signals through the provider supervisor.
    if result.returncode < 0:
        os.kill(os.getpid(), -result.returncode)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
