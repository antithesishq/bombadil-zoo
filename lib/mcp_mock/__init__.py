"""Config-driven, newline-delimited MCP stdio fixtures for zoo harnesses."""

import json
import sys
from typing import Any


PUBLIC_FIELDS = ("name", "description", "inputSchema")


def result_for(tool: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    text = tool.get("text", "")
    if echo := tool.get("echo_argument"):
        text += str(arguments.get(echo, ""))
    text *= tool.get("repeat", 1)
    return {
        "content": [{"type": "text", "text": text}],
        **({"isError": True} if tool.get("isError") else {}),
    }


def serve(input_stream=None, output_stream=None, *, config: dict[str, Any]) -> None:
    """Serve one MCP stdio session until the client closes its input."""
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    tools = config.get("tools", [])
    by_name = {tool["name"]: tool for tool in tools}
    for line in input_stream:
        try:
            request = json.loads(line)
        except ValueError:
            continue
        method = request.get("method")
        ident = request.get("id")
        if ident is None:
            continue
        if method == "initialize":
            result = {
                "protocolVersion": request.get("params", {}).get("protocolVersion", "2025-03-26"),
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": config.get("name", "zoo-mcp"),
                    "version": config.get("version", "1.0"),
                },
            }
        elif method == "tools/list":
            result = {"tools": [{key: tool[key] for key in PUBLIC_FIELDS if key in tool}
                                for tool in tools]}
        elif method == "tools/call":
            params = request.get("params", {})
            tool = by_name.get(params.get("name"))
            if tool is None:
                result = {"content": [{"type": "text", "text": "Unknown fixture tool"}],
                          "isError": True}
            else:
                result = result_for(tool, params.get("arguments", {}))
        elif method == "ping":
            result = {}
        else:
            response = {"jsonrpc": "2.0", "id": ident,
                        "error": {"code": -32601, "message": "Method not found"}}
            print(json.dumps(response), file=output_stream, flush=True)
            continue
        response = {"jsonrpc": "2.0", "id": ident, "result": result}
        print(json.dumps(response, ensure_ascii=False), file=output_stream, flush=True)


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as config_file:
        config = json.load(config_file)
    serve(config=config)


if __name__ == "__main__":
    main()
