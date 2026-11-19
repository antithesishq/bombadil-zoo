"""Private, deterministic OpenAI Chat Completions fixtures for zoo harnesses.

A router receives each decoded completion request and returns a Stream or
HTTPResponse. The package owns the loopback server and wire format; harnesses
own their scenarios, tool names, and client configuration.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time
from typing import Any, Callable, TypeAlias


JsonObject: TypeAlias = Mapping[str, Any]
Event: TypeAlias = JsonObject | str


@dataclass(frozen=True)
class Stream:
    """SSE events. Strings are sent verbatim; mappings are JSON-encoded."""

    events: Iterable[Event]
    delay: float = 0
    done: bool = True


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    body: bytes
    content_type: str = "application/json"

    @classmethod
    def json(cls, status: int, body: Any) -> "HTTPResponse":
        return cls(status, json.dumps(body, ensure_ascii=False).encode())


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Any
    id: str | None = None


def error(status: int, message: str) -> HTTPResponse:
    return HTTPResponse.json(status, {"error": {"message": message, "type": "fixture_error"}})


def chunk(delta: JsonObject, finish_reason: str | None = None,
          model: str = "zoo-mock") -> JsonObject:
    return {
        "id": "chatcmpl-zoo", "object": "chat.completion.chunk",
        "created": 1700000000, "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def usage_chunk(prompt_tokens: int, completion_tokens: int,
                model: str = "zoo-mock") -> JsonObject:
    return {
        "id": "chatcmpl-zoo", "object": "chat.completion.chunk",
        "created": 1700000000, "model": model, "choices": [],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _pieces(text: str, size: int) -> Iterable[str]:
    if size < 1:
        raise ValueError("chunk_size must be positive")
    for offset in range(0, len(text), size):
        yield text[offset:offset + size]


def text(content: str, *, chunk_size: int = 24, delay: float = 0,
         reasoning: str | None = None, usage: tuple[int, int] | None = None,
         finish_reason: str = "stop", model: str = "zoo-mock") -> Stream:
    """Build a streamed assistant reply, including optional reasoning and usage."""
    events: list[Event] = [chunk({"role": "assistant", "content": ""}, model=model)]
    if reasoning is not None:
        events.extend(chunk({"reasoning_content": part}, model=model)
                      for part in _pieces(reasoning, chunk_size))
    events.extend(chunk({"content": part}, model=model)
                  for part in _pieces(content, chunk_size))
    events.append(chunk({}, finish_reason, model))
    if usage is not None:
        events.append(usage_chunk(*usage, model=model))
    return Stream(events, delay)


def tool_calls(calls: Iterable[ToolCall | tuple[str, Any]], *, chunk_size: int = 64,
               delay: float = 0, content: str | None = None,
               model: str = "zoo-mock") -> Stream:
    """Build incremental function calls, optionally preceded by assistant text."""
    events: list[Event] = []
    if content is not None:
        events.append(chunk({"role": "assistant", "content": ""}, model=model))
        events.extend(chunk({"content": part}, model=model)
                      for part in _pieces(content, chunk_size))
    for index, item in enumerate(calls):
        call = item if isinstance(item, ToolCall) else ToolCall(*item)
        arguments = (call.arguments if isinstance(call.arguments, str) else
                     json.dumps(call.arguments, ensure_ascii=False))
        for offset in range(0, max(len(arguments), 1), chunk_size):
            part: dict[str, Any] = {
                "index": index,
                "function": {"arguments": arguments[offset:offset + chunk_size]},
            }
            delta: dict[str, Any] = {"tool_calls": [part]}
            if offset == 0:
                part["id"] = call.id or f"call_zoo_{index}"
                part["type"] = "function"
                part["function"]["name"] = call.name
                delta["role"] = "assistant"
                delta["content"] = None
            events.append(chunk(delta, model=model))
    events.append(chunk({}, "tool_calls", model))
    return Stream(events, delay)


Router: TypeAlias = Callable[[dict[str, Any]], Stream | HTTPResponse]


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, owner: "OpenAIMock"):
        self.owner = owner
        super().__init__(("127.0.0.1", 0), _Handler)


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, format: str, *args: Any) -> None:
        if self.server.owner.log_requests:
            super().log_message(format, *args)

    def do_GET(self) -> None:
        if self.path == "/v1/models":
            self._reply(HTTPResponse.json(200, {
                "object": "list",
                "data": [{"id": self.server.owner.model, "object": "model",
                          "created": 0, "owned_by": "zoo"}],
            }))
        else:
            self._reply(error(404, "Unknown fixture route"))

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._reply(error(404, "Unknown fixture route"))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
        except (ValueError, UnicodeDecodeError):
            self._reply(error(400, "Invalid JSON request"))
            return
        response = self.server.owner.router(request)
        if isinstance(response, HTTPResponse):
            self._reply(response)
        elif isinstance(response, Stream):
            self._stream(response)
        else:
            raise TypeError("router must return Stream or HTTPResponse")

    def _reply(self, response: HTTPResponse) -> None:
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        try:
            self.wfile.write(response.body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _stream(self, response: Stream) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for event in response.events:
                data = json.dumps(event, ensure_ascii=False) if isinstance(event, Mapping) else event
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
                if response.delay:
                    time.sleep(response.delay)
            if response.done:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # Cancellation is an expected fuzz action.


class OpenAIMock:
    """A loopback-only fixture server. Start and stop it with a with block."""

    def __init__(self, router: Router, *, model: str = "zoo-mock",
                 log_requests: bool = True):
        self.router = router
        self.model = model
        self.log_requests = log_requests
        self._server = _Server(self)
        self._thread: Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    def __enter__(self) -> "OpenAIMock":
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
