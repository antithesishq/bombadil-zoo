# OpenAI mock

A stdlib-only, loopback OpenAI Chat Completions fixture server for zoo harnesses.
For now it only covers HTTP and SSE behavior.
Each harness keeps its own scenarios, tool names, permission decisions, and client configuration.

**In the future we might move more things into this mock**

```python
from openai_mock import OpenAIMock, text, tool_calls


def route(request):
    prompt = request["messages"][-1]["content"]
    if prompt == "zoo:tool":
        return tool_calls([("read_file", {"path": "README.md"})], chunk_size=16)
    return text("ZOO_MOCK_OK 中文", reasoning="fixture", usage=(10, 2))


with OpenAIMock(route) as server:
    configure_client(base_url=server.base_url, model="zoo-mock")
    run_client()
```

`text` and `tool_calls` create streaming responses. Return `Stream` directly for
malformed events, disconnects, or custom chunks, and `HTTPResponse` or `error`
for non-streaming responses. `ToolCall` accepts structured arguments or raw JSON
and an optional caller-chosen ID. All servers use an ephemeral loopback port;
no credentials or external network access are needed.

Run the contract tests with:

```sh
PYTHONPATH=lib python3 -m unittest discover -s lib/openai_mock -v
```
