"""Contract tests for the shared OpenAI fixture wire protocol."""

import json
import unittest
import urllib.error
import urllib.request

from openai_mock import OpenAIMock, Stream, ToolCall, chunk, error, text, tool_calls


def events(body):
    return [json.loads(line[6:]) for line in body.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"]


class OpenAIMockTest(unittest.TestCase):
    def post(self, server, payload=None, path="/chat/completions", raw=None):
        data = raw if raw is not None else json.dumps(payload or {
            "model": "zoo-mock", "stream": True,
            "messages": [{"role": "user", "content": "fixture"}],
        }).encode()
        request = urllib.request.Request(
            server.base_url + path, data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read().decode()
        except urllib.error.HTTPError as failure:
            try:
                return failure.code, failure.headers, failure.read().decode()
            finally:
                failure.close()

    def test_models_and_streamed_unicode_reasoning_and_usage(self):
        def router(request):
            return text("blåbær 中文 👩‍💻", chunk_size=3,
                        reasoning="think 中文", usage=(12, 5))

        with OpenAIMock(router, log_requests=False) as server:
            with urllib.request.urlopen(server.base_url + "/models", timeout=5) as response:
                models = json.load(response)
            status, headers, body = self.post(server)
        self.assertEqual(models["data"][0]["id"], "zoo-mock")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/event-stream")
        chunks = events(body)
        content = "".join(c["choices"][0]["delta"].get("content", "")
                          for c in chunks if c["choices"])
        reasoning = "".join(c["choices"][0]["delta"].get("reasoning_content", "")
                            for c in chunks if c["choices"])
        self.assertEqual(content, "blåbær 中文 👩‍💻")
        self.assertEqual(reasoning, "think 中文")
        self.assertEqual(chunks[-2]["choices"][0]["finish_reason"], "stop")
        self.assertEqual(chunks[-1]["usage"]["total_tokens"], 17)
        self.assertTrue(body.endswith("data: [DONE]\n\n"))

    def test_batched_tool_calls_reassemble_and_follow_text(self):
        calls = [
            ToolCall("write_file", {"path": "中文", "content": "👩‍💻"}, "call-write"),
            ("shell", '{"command":"printf ok"}'),
        ]

        def router(request):
            return tool_calls(calls, chunk_size=7, content="Working 中文")

        with OpenAIMock(router, log_requests=False) as server:
            _, _, body = self.post(server)
        deltas = [c["choices"][0]["delta"] for c in events(body) if c["choices"]]
        self.assertEqual("".join(d.get("content", "") or "" for d in deltas), "Working 中文")
        names = {}
        arguments = {0: "", 1: ""}
        ids = {}
        for delta in deltas:
            for call in delta.get("tool_calls", []):
                index = call["index"]
                arguments[index] += call["function"].get("arguments", "")
                if "name" in call["function"]:
                    names[index] = call["function"]["name"]
                    ids[index] = call["id"]
        self.assertEqual(names, {0: "write_file", 1: "shell"})
        self.assertEqual(ids, {0: "call-write", 1: "call_zoo_1"})
        self.assertEqual(json.loads(arguments[0]), calls[0].arguments)
        self.assertEqual(json.loads(arguments[1]), {"command": "printf ok"})
        self.assertEqual(deltas[-1], {})
        self.assertEqual(events(body)[-1]["choices"][0]["finish_reason"], "tool_calls")

    def test_http_errors_and_invalid_requests(self):
        with OpenAIMock(lambda request: error(429, "slow down"), log_requests=False) as server:
            status, _, body = self.post(server)
            self.assertEqual(status, 429)
            self.assertEqual(json.loads(body)["error"]["message"], "slow down")
            status, _, body = self.post(server, path="/unknown")
            self.assertEqual(status, 404)
            status, _, body = self.post(server, raw=b"not-json")
            self.assertEqual(status, 400)
            status, _, _ = self.post(server, path="/unknown", raw=b"not-json")
            self.assertEqual(status, 404)

    def test_malformed_disconnect_and_custom_chunks(self):
        def router(request):
            prompt = request["messages"][-1]["content"]
            if prompt == "malformed":
                return Stream(["{not valid json"])
            if prompt == "disconnect":
                return Stream([chunk({"content": "partial"})], done=False)
            return Stream(["plain event"], done=False)

        with OpenAIMock(router, log_requests=False) as server:
            for prompt, expected in [
                ("malformed", "data: {not valid json\n\ndata: [DONE]\n\n"),
                ("disconnect", 'data: {"id": "chatcmpl-zoo"'),
                ("custom", "data: plain event\n\n"),
            ]:
                with self.subTest(prompt=prompt):
                    payload = {"messages": [{"role": "user", "content": prompt}]}
                    _, _, body = self.post(server, payload)
                    self.assertIn(expected, body)
                    if prompt != "malformed":
                        self.assertNotIn("[DONE]", body)


if __name__ == "__main__":
    unittest.main()
