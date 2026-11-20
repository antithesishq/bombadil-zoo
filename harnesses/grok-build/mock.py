"""Run unmodified Grok against a private OpenAI-compatible fixture server."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import time
import zlib


MARKDOWN = """ZOO_MOCK_OK

# Streaming fixture

**bold** _italic_ `inline code` [link](https://example.invalid)

```python
print("hello")
```

| Name | Value |
| --- | --- |
| Unicode | blåbær 中文 👩‍💻 é |

- first item
- second item

Math: $x^2 + y^2$. Done.
"""


WIDE = "中文👩‍💻é" * 40
# Rendering fixtures. Each one targets a layout path with awkward geometry:
# wide cells at wrap boundaries, unbreakable lines, ragged tables, deep nesting.
FIXTURES = {
    "mermaid": """ZOO_MOCK_MERMAID

```mermaid
flowchart LR
  A[Start 中文] -->|yes 👩‍💻| B{Decision with a very long label that cannot fit in a narrow terminal}
  B --> C((Circle))
  B -.-> D[(Database)]
  C ==> E>Flag]
  D --> A
  subgraph one [Group é]
    E --> F
    F --> E
  end
```

```mermaid
sequenceDiagram
  participant A as Alice 👩‍💻
  participant B as 中文中文中文中文中文
  A->>B: hello
  B-->>A: a reply that is far too long to fit between two lifelines in any terminal
  Note over A,B: note
  loop every minute
    A->>A: self
  end
```

```mermaid
graph TD
  A-->A
  A-->
  -->B
```

```mermaid
```

```mermaid
pie title Pets
  "Dogs" : 386
  "Cats" : 0
  "" : -1
```

```mermaid
gantt
  dateFormat YYYY-MM-DD
  section S
  Task :a1, 2026-01-01, 0d
```
""",
    "table": """ZOO_MOCK_TABLE

| a | b | c | d | e | f | g | h | i | j | k | l | m | n | o | p |
|:--|--:|:-:|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 中文中文中文中文 | 👩‍💻👩‍💻👩‍💻 | `code` | **b** | | | x | y | z | 1 | 2 | 3 | 4 | 5 | 6 |
| ragged | row |
| too | many | cells | in | this | row | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
| """ + "unbreakable" * 40 + """ | x |

| |
|-|
| |

|||
|-|-|

| solo |
|------|
| a \\| b | 
""",
    "nested": """ZOO_MOCK_NESTED

""" + "".join("  " * i + f"- level {i} 中文\n" for i in range(40)) + """
""" + "".join(">" * i + f" quote {i}\n\n" for i in range(1, 30)) + """
1. one
   1. two
      1. three
         ```rust
         fn deep() {}
         ```
         | t | u |
         |---|---|
         | 1 | 2 |

- [ ] task
- [x] done
  > quote in list
  > - list in quote in list

# h1
## h2
### h3
#### h4
##### h5
###### h6
####### h7

---
***
<details><summary>html</summary><b>bold</b></details>

[^1]: footnote
Term
: definition
""",
    "unicode": """ZOO_MOCK_UNICODE

""" + WIDE + """

Combining: a\u0301\u0302\u0303\u0304\u0305\u0306\u0307\u0308 Z\u0351\u036b\u0343\u036a\u0302\u036b\u033d\u034f\u0334\u0319\u0324\u031e
Zero width: a\u200bb\u200cc\u200dd\ufeffe\u2060f
RTL: \u05e9\u05dc\u05d5\u05dd \u0645\u0631\u062d\u0628\u0627 \u202eoverride\u202c \u2067isolate\u2069
Flags: 🇳🇴🇯🇵 🏳️‍🌈 👨‍👩‍👧‍👦 👍🏽 ☝🏿 1️⃣ ©️ ✈︎
Wide: ｆｕｌｌｗｉｄｔｈ 한국어 ｶﾀｶﾅ \u3000ideographic space
Tabs:\ta\tb\t\tc
Controls: bell\x07 bs\x08 vt\x0b ff\x0c cr\rOVER esc\x1b[31mred\x1b[0m osc\x1b]0;title\x07 csi\x1b[2J\x1b[H del\x7f
C1: \x85\x9b31m\x9c
Astral: 𝔘𝔫𝔦𝔠𝔬𝔡𝔢 𓀀 \U000e0041 \U0010ffff
Lone: \ufffd \ufffe
""" + "👩‍💻" * 200 + """
""",
    "code": """ZOO_MOCK_CODE

```
no language
```

```nosuchlanguage
??? 
```

```diff
--- a/hello.py
+++ b/hello.py
@@ -1 +1,2 @@
-print("hello")
+print("hello 中文")
+""" + "x" * 900 + """
```

```python
""" + "".join(f"def f{i}(a, b):\n\treturn a + b  # {'中' * (i % 50)}\n" for i in range(150)) + """```

~~~~markdown
```nested fence```
~~~~

`unterminated inline

$$
\\begin{aligned} x &= \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a} \\\\ \\sum_{i=0}^{\\infty} \\end{aligned}
$$

\\( \\frac{1}{0} \\) and \\[ unterminated

```rust
fn unterminated() {
""",
    "long": "ZOO_MOCK_LONG\n\n" + "".join(
        f"## Section {i}\n\nParagraph {i} " + "word " * 60 + "\n\n" for i in range(120)),
    "links": """ZOO_MOCK_LINKS

[a](https://example.invalid/""" + "p/" * 300 + """) ![img](file:///nonexistent.png) <https://example.invalid>
[ref][1] [empty]() [](x) [nested [brackets]](y) https://example.invalid/?q=中文&x=%ZZ
![](data:image/png;base64,AAAA) file:///etc/passwd hello.py:1 ./hello.py README.md#L1

[1]: https://example.invalid "title"
""",
    "empty": "",
    "blank": "\n\n\n   \n\t\n",
}


def call(name, **arguments):
    return (name, json.dumps(arguments, ensure_ascii=False))


QUESTION = {"question": "Which fixture 中文?", "options": [
    {"label": "A", "description": "first", "preview": "```rust\nfn a() {}\n```\n" + "x" * 300},
    {"label": "B 👩‍💻", "description": "second " * 40, "preview": None},
    {"label": "", "description": ""},
]}
# Tool-call fixtures: (name, raw argument JSON) per call in one assistant turn.
TOOLS = {
    "tool-call": [call("run_terminal_command", command="printf ZOO_MOCK_TOOL_DONE",
                       description="Print the fixture marker")],
    "tool-big": [call("run_terminal_command", command="seq 1 4000",
                      description="Long output")],
    "tool-ansi": [call("run_terminal_command",
                       command="printf '\\033[31mred\\033[0m\\r\\n\\033[2J\\033[H\\033[?1049h"
                               "\\033]0;t\\007\\tTAB\\r OVER\\b\\b\\n中文👩‍💻\\n'; "
                               "head -c 3000 /dev/urandom; printf '%04000d' 0",
                       description="Escape sequences, binary, and one very long line")],
    "tool-slow": [call("run_terminal_command",
                       command="for i in 1 2 3 4 5 6; do echo tick $i; sleep 0.5; done",
                       description="Streaming output")],
    "tool-fail": [call("run_terminal_command", command="echo out; echo err >&2; exit 3",
                       description="Failing command")],
    "tool-write": [call("write", file_path="zoo-new.md",
                        content="# new\n" + "line 中文\n" * 200)],
    "tool-edit": [call("search_replace", file_path="hello.py", old_string='print("hello")',
                       new_string='print("hello")\nprint("中文 👩‍💻")\n' + "y = 1\n" * 80,
                       replace_all=True)],
    "tool-edit-miss": [call("search_replace", file_path="nope/missing.py",
                            old_string="a", new_string="b")],
    "tool-read": [call("read_file", target_file="README.md"),
                  call("read_file", target_file="/nonexistent", offset=-5, limit=0),
                  call("list_dir", target_directory="."),
                  call("grep", pattern="(", path="."),
                  call("grep", pattern="hello", **{"-C": 3, "-i": True})],
    "tool-todo": [call("todo_write", merge=False, todos=[
        {"id": str(i), "content": f"todo {i} " + "中文 " * (i * 3),
         "status": ["pending", "in_progress", "completed", "cancelled"][i % 4]}
        for i in range(30)])],
    "tool-todo-odd": [call("todo_write", merge=True, todos=[
        {"id": "", "content": None, "status": None}, {"id": "1"}, {"id": "1"},
        {"id": "x" * 500, "content": "\n\n\t", "status": "completed"}])],
    "tool-ask": [call("ask_user_question", questions=[QUESTION])],
    "tool-ask-multi": [call("ask_user_question", questions=[
        QUESTION | {"multi_select": True},
        {"question": "Q" * 400, "options": [
            {"label": f"option {i}", "description": "d"} for i in range(40)]},
        {"question": "", "options": []},
    ])],
    "tool-plan": [call("enter_plan_mode")],
    "tool-plan-exit": [call("exit_plan_mode")],
    "tool-many": [call("run_terminal_command", command=f"echo parallel {i}",
                       description=f"Parallel {i}") for i in range(12)],
    "tool-unknown": [call("no_such_tool", x=1), ("", "{}")],
    "tool-bad-args": [("run_terminal_command", '{"command": "echo x", "descr'),
                      ("todo_write", '{"todos": "not a list"}'),
                      ("ask_user_question", '{"questions": [{"question": 1, "options": {}}]}'),
                      ("read_file", "[]"), ("write", "null"), ("grep", "")],
    "tool-search": [call("search_tool", query="anything", limit=0),
                    call("use_tool", tool_name="nope", tool_input={}),
                    call("scheduler_list"),
                    call("get_command_or_subagent_output", task_ids=["nope"], timeout_ms=1),
                    call("kill_command_or_subagent", task_id="nope")],
    "tool-mcp": [call("search_tool", query="zoo"),
                 call("use_tool", tool_name="zoo_echo", tool_input={"text": "中文 👩‍💻"}),
                 call("use_tool", tool_name="zoo_table", tool_input={}),
                 call("use_tool", tool_name="zoo_fail", tool_input={}),
                 call("use_tool", tool_name="mcp__zoo__zoo_echo", tool_input={"text": "x"})],
    "tool-background": [call("run_terminal_command", command="sleep 30; echo late",
                             description="Outlives its wait", block_until_ms=0),
                        call("monitor", command="echo watched; sleep 1; echo again",
                             description="Monitor", timeout_ms=2000, persistent=False)],
}
# A long agent turn: one tool call per round, each with some text before it,
# the way a model narrates while it works. The transcript ends up with a
# dozen tool blocks of different kinds.
CHAIN = [
    call("list_dir", target_directory="."),
    call("read_file", target_file="hello.py"),
    call("grep", pattern="hello", path="."),
    call("todo_write", merge=False, todos=[
        {"id": str(i), "content": f"step {i}", "status": "pending"} for i in range(6)]),
    call("run_terminal_command", command="git status --short | head -20",
         description="Check the working tree"),
    call("search_replace", file_path="hello.py", old_string='print("hello")',
         new_string='print("hello, chain")'),
    call("todo_write", merge=True, todos=[
        {"id": str(i), "status": "completed"} for i in range(4)]),
    call("write", file_path="chain.md", content="# Chain\n\nWritten by the fixture.\n"),
    call("run_terminal_command", command="cat chain.md; seq 1 60",
         description="Show the result"),
    call("read_file", target_file="many/file-1.txt"),
    call("list_dir", target_directory="deep/a/b/c"),
    call("run_terminal_command", command="git diff --stat",
         description="Summarize the change"),
]
# Token counts reported with the final chunk. The configured window is 128000.
USAGE = {
    "usage-small": (12, 5),
    "usage-near": (127990, 9),
    "usage-full": (128000, 0),
    "usage-over": (500000, 4096),
    "usage-zero": (0, 0),
    "usage-huge": (2 ** 53, 2 ** 53),
}
ONELINE = "ZOO_MOCK_ONELINE " + "abcdefghij" * 800 + " https://example.invalid/" + "seg/" * 400
FIXTURES["oneline"] = ONELINE
SCENARIOS = sorted(
    ["markdown", "rate-limit", "server-error", "malformed", "disconnect", "reasoning", "slow",
     "tiny", "truncated", "html-error", "chain", "text-tool", *USAGE, *FIXTURES, *TOOLS],
    key=len, reverse=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # The launcher's stderr tee retains these records with the run ID.
        print("zoo-mock:", format % args, file=sys.stderr, flush=True)

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/v1/models":
            self.reply(200, {"object": "list", "data": [
                {"id": "zoo-mock", "object": "model", "created": 0,
                 "owned_by": "zoo"}
            ]})
        else:
            self.reply(404, {"error": {"message": "Unknown fixture route"}})

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path != "/v1/chat/completions":
            self.reply(404, {"error": {"message": "Unknown fixture route"}})
            return
        messages = request.get("messages", [])
        users = [m.get("content", "") for m in messages if m.get("role") == "user"]
        prompt = json.dumps(users[-1] if users else "", ensure_ascii=False)
        # Longest name first, so zoo:tool-ask-multi is not read as zoo:tool-ask.
        # A prompt without a marker gets a fixture chosen by its hash, so that
        # generated text reaches every fixture and the same prompt always gets
        # the same one. Tool calls go only to requests that offer tools.
        names = SCENARIOS if request.get("tools") else [
            s for s in SCENARIOS if s not in TOOLS and s not in ("chain", "text-tool")]
        scenario = next((s for s in SCENARIOS if f"zoo:{s}" in prompt),
                        names[zlib.crc32(prompt.encode()) % len(names)])
        # Assistant messages since the latest user message: the round of this turn.
        roles = [m.get("role") for m in messages]
        last_user = max((i for i, r in enumerate(roles) if r == "user"), default=-1)
        rounds = roles[last_user + 1:].count("assistant")
        if messages and messages[-1].get("role") == "tool":
            # Finish the mocked agent turn instead of issuing the same call
            # forever. Only the chain fixture keeps going, for a fixed length.
            if scenario != "chain" or rounds >= len(CHAIN):
                scenario = "markdown"
        self.log_message("scenario=%s stream=%s model=%s", scenario,
                         request.get("stream"), request.get("model"))
        if scenario in ("rate-limit", "server-error"):
            self.reply(429 if scenario == "rate-limit" else 500,
                       {"error": {"message": f"ZOO_MOCK_{scenario}", "type": "fixture_error"}})
            return
        if scenario == "html-error":
            data = b"<html><body><h1>502 Bad Gateway</h1>" + b"<p>x</p>" * 400 + b"</body></html>"
            self.send_response(502)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def event(data):
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()

        def chunk(delta, finish=None):
            event(json.dumps({
                "id": "chatcmpl-zoo", "object": "chat.completion.chunk",
                "created": 1700000000, "model": "zoo-mock",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }, ensure_ascii=False))

        try:
            if scenario == "malformed":
                event("{not valid json")
                event("[DONE]")
                return
            calls = TOOLS.get(scenario)
            if scenario == "chain":
                calls = [CHAIN[rounds % len(CHAIN)]]
                chunk({"role": "assistant",
                       "content": f"ZOO_MOCK_CHAIN round {rounds + 1} of {len(CHAIN)}. "})
                chunk({"content": "Next I will **look** at `the project`.\n\n"})
            if scenario == "text-tool":
                # Prose, a code block, and then a tool call in the same message.
                calls = TOOLS["tool-call"]
                chunk({"role": "assistant", "content": ""})
                for offset in range(0, len(MARKDOWN), 13):
                    chunk({"content": MARKDOWN[offset:offset + 13]})
            if calls is not None:
                for index, (name, arguments) in enumerate(calls):
                    for offset in range(0, max(len(arguments), 1), 7):
                        tool = {"index": index, "function": {
                            "arguments": arguments[offset:offset + 7],
                        }}
                        delta = {"tool_calls": [tool]}
                        if offset == 0:
                            if scenario in TOOLS:
                                delta["role"] = "assistant"
                                delta["content"] = None
                            tool["id"] = f"call_zoo_{rounds}_{index}"
                            tool["type"] = "function"
                            tool["function"]["name"] = name
                        chunk(delta)
                chunk({}, "tool_calls")
                event("[DONE]")
                return
            if scenario == "truncated":
                # A finish reason of "length" and a final event cut mid-JSON.
                chunk({"role": "assistant", "content": "ZOO_MOCK_TRUNCATED **unclosed `mark"})
                chunk({}, "length")
                self.wfile.write(b'data: {"id": "chatcmpl-zoo", "choi')
                self.wfile.flush()
                return
            if scenario == "reasoning":
                chunk({"role": "assistant", "content": "",
                       "reasoning_content": "ZOO_MOCK_REASONING\nSplit reasoning deltas."})
                chunk({"reasoning_content": " More thought 🧠."})
            else:
                chunk({"role": "assistant", "content": ""})
            if scenario == "disconnect":
                chunk({"content": "ZOO_MOCK_PARTIAL"})
                return
            # "tiny" streams one character per event, so every partial Markdown
            # state is rendered: half a fence, half a table row, half an emoji.
            text = FIXTURES.get(scenario, MARKDOWN)
            size = 1 if scenario == "tiny" else 13 if len(text) < 4000 else 97
            for offset in range(0, len(text), size):
                chunk({"content": text[offset:offset + size]})
                time.sleep(0.05 if scenario == "slow" else 0.002)
            chunk({}, "stop")
            if scenario in USAGE:
                prompt_tokens, completion_tokens = USAGE[scenario]
                event(json.dumps({
                    "id": "chatcmpl-zoo", "object": "chat.completion.chunk",
                    "created": 1700000000, "model": "zoo-mock", "choices": [],
                    "usage": {"prompt_tokens": prompt_tokens,
                              "completion_tokens": completion_tokens,
                              "total_tokens": prompt_tokens + completion_tokens},
                }))
            event("[DONE]")
        except (BrokenPipeError, ConnectionResetError):
            # Cancellation is an expected part of a TUI campaign.
            self.log_message("client cancelled stream")


# A stdio MCP server with three tools, written into the run's home. It gives
# /mcps a populated server, and use_tool something real to call.
MCP_SERVER = r"""
import json, sys

TOOLS = [
    {"name": "zoo_echo", "description": "Echo the text back. 中文 👩‍💻 " + "Long description. " * 20,
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}},
    {"name": "zoo_table", "description": "Return a Markdown table.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "zoo_fail", "description": "Always fails.",
     "inputSchema": {"type": "object", "properties": {}}},
]
for line in sys.stdin:
    try:
        message = json.loads(line)
    except ValueError:
        continue
    method, ident = message.get("method"), message.get("id")
    if ident is None:
        continue
    if method == "initialize":
        result = {"protocolVersion": message["params"].get("protocolVersion", "2025-03-26"),
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "zoo-mcp", "version": "1.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name = message["params"].get("name")
        if name == "zoo_fail":
            result = {"content": [{"type": "text", "text": "ZOO_MCP_FAIL"}], "isError": True}
        elif name == "zoo_table":
            result = {"content": [{"type": "text", "text": "| a | b |\n|---|---|\n| 1 | 中文 |\n" * 30}]}
        else:
            text = message["params"].get("arguments", {}).get("text", "")
            result = {"content": [{"type": "text", "text": "ZOO_MCP_ECHO " + str(text)}]}
    elif method == "ping":
        result = {}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": ident,
                          "error": {"code": -32601, "message": "Method not found"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}), flush=True)
"""

# A status line script of the kind people port from other tools: colour,
# glyphs, wide characters, and a second line.
STATUS_LINE = r"""input=$(cat)
printf '\033[1;36m⚡ zoo\033[0m │ \033[33m main ±2\033[0m │ 中文 👩‍💻 │ %s │ $0.42\n' "$(date +%H:%M:%S)"
printf '\033[2m%s cols · %s\033[0m\n' "${COLUMNS:-?}" "${#input} bytes of context"
"""


def seed_home(home, project):
    """What an established user has: skills, commands, hooks, MCP servers."""
    (home / "statusline.sh").write_text(STATUS_LINE)
    (home / "zoo-mcp.py").write_text(MCP_SERVER)
    for name, description in (("zoo-review", "Review the current change. Use for /zoo-review."),
                              ("zoo-中文-skill", "A skill with a wide name 👩‍💻. " + "Long. " * 40)):
        skill = home / "skills" / name
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nSay zoo:markdown.\n")
    commands = home / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    (commands / "zoo-cmd.md").write_text("Answer zoo:markdown and nothing else.\n")
    (commands / "zoo-chain.md").write_text("Run zoo:chain for $ARGUMENTS.\n")
    local = project / ".grok" / "commands"
    local.mkdir(parents=True, exist_ok=True)
    (local / "deploy.md").write_text("---\ndescription: Deploy the zoo\n---\n\nzoo:tool-call\n")
    hooks = home / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "zoo.json").write_text(json.dumps({"hooks": {
        "PreToolUse": [{"hooks": [{"type": "command", "command": "echo zoo-pre-hook", "timeout": 5}]}],
        "PostToolUse": [{"matcher": "run_terminal_command", "hooks": [
            {"type": "command", "command": "echo zoo-post-hook 中文; exit 0", "timeout": 5}]}],
    }}))


def main():
    # A caught handler resets to SIG_DFL on exec in Grok. Unlike SIG_IGN,
    # this protects only the wrapper when Grok restores terminal ISIG.
    signal.signal(signal.SIGINT, lambda *_: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    home = Path(os.environ["HOME"]) / ".grok"
    home.mkdir(parents=True, exist_ok=True)
    seed_home(home, Path.cwd())
    (home / "config.toml").write_text(f'''[cli]
auto_update = false
[models]
default = "zoo-mock"
max_retries = 0
[model.zoo-mock]
model = "zoo-mock"
name = "Zoo Mock"
base_url = "{base_url}"
api_key = "zoo-not-a-real-key"
api_backend = "chat_completions"
context_window = 128000
[model.zoo-alt]
model = "zoo-alt"
name = "Zoo Alternate 中文 with a long display name"
base_url = "{base_url}"
api_key = "zoo-not-a-real-key"
api_backend = "chat_completions"
context_window = 8000
[ui.status_line]
type = "command"
command = "/bin/sh {home}/statusline.sh"
refresh_interval = 1
[mcp_servers.zoo]
command = "{sys.executable}"
args = ["{home}/zoo-mcp.py"]
[mcp_servers.zoo-missing]
command = "/nonexistent/zoo-mcp"
startup_timeout_sec = 2
[mcp_servers.zoo-remote]
url = "{base_url}/mcp"
[features]
telemetry = false
remote_fetch = false
[session]
load_envrc = false
''')
    env = os.environ | {
        "GROK_HOME": str(home),
        "XAI_API_KEY": "zoo-not-a-real-key",
        "GROK_MODELS_BASE_URL": base_url,
        "GROK_CLI_CHAT_PROXY_BASE_URL": base_url,
        "GROK_TELEMETRY_ENABLED": "false",
        "GROK_TELEMETRY_TRACE_UPLOAD": "false",
    }
    try:
        status = subprocess.call(sys.argv[1:], env=env)
    finally:
        server.shutdown()
        server.server_close()
    if status < 0:
        # Keep the target's fatal signal observable by Bombadil.
        signum = -status
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    return status


if __name__ == "__main__":
    sys.exit(main())
