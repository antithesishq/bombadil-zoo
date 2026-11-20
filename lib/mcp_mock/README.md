# MCP mock

A stdlib-only MCP stdio fixture server. It handles newline-delimited JSON-RPC,
initialization, tool catalogs, calls, pings, and client EOF. Harnesses provide
tool definitions in JSON; no child SDK or external service is required.

```json
{
  "name": "zoo-mcp",
  "tools": [
    {
      "name": "echo",
      "description": "Return fixture text",
      "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
      "text": "ZOO_MCP_ECHO ",
      "echo_argument": "text"
    },
    {
      "name": "fail",
      "description": "Return an expected failure",
      "inputSchema": {"type": "object"},
      "text": "ZOO_MCP_EXPECTED_FAILURE",
      "isError": true
    }
  ]
}
```

Run `python3 -m mcp_mock config.json` with `lib` on `PYTHONPATH`. `repeat`
repeats a result string, and `echo_argument` appends one argument. These
fixture-only fields are omitted from `tools/list`.

Run the contract test with:

```sh
PYTHONPATH=lib python3 -m unittest discover -s lib/mcp_mock -v
```
