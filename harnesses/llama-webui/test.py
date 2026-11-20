import argparse
import json
import os
from pathlib import Path
import shlex
from typing import Any


def duration(value):
    try:
        seconds = int(value[:-1]) * {"s": 1, "m": 60, "h": 3600}[value[-1]]
    except (ValueError, KeyError, IndexError):
        raise argparse.ArgumentTypeError("expected a duration such as 30s or 5m")
    if seconds <= 0:
        raise argparse.ArgumentTypeError("duration must be positive")
    return seconds


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


request: dict[str, Any] = (
    json.loads(Path(os.environ["LLAMA_WEBUI_REQUEST"]).read_text())
    if "LLAMA_WEBUI_REQUEST" in os.environ
    else {"args": ["--time-limit-fuzz", "25s", "--time-limit-run", "20s"]}
)
parser = argparse.ArgumentParser()
parser.add_argument("--time-limit-fuzz", type=duration, default=300)
parser.add_argument("--time-limit-run", type=duration, default=20)
parser.add_argument("--parallelism", type=positive, default=1)
parser.add_argument("--swarm", action="store_true")
parser.add_argument("--width", type=positive, default=1280)
parser.add_argument("--height", type=positive, default=800)
parser.add_argument(
    "--chrome-virtual-time-policy",
    choices=["Advance", "Pause", "PauseIfNetworkFetchesPending"],
    default="PauseIfNetworkFetchesPending",
)
options = parser.parse_args(request["args"])
saved_args = list(request["args"])
if not any(
    arg == "--chrome-virtual-time-policy"
    or arg.startswith("--chrome-virtual-time-policy=")
    for arg in saved_args
):
    saved_args += [
        "--chrome-virtual-time-policy",
        options.chrome_virtual_time_policy,
    ]
saved_request = {**request, "args": saved_args}

machine.start()
machine.wait_for_unit("llama-webui.service")
machine.wait_until_succeeds("curl -fsS http://127.0.0.1:8080/health", timeout=120)
machine.succeed("mkdir -m 700 -p /tmp/artifacts")
try:
    machine.succeed("cp /etc/llama-webui-zoo/builds.json /tmp/artifacts/builds.json")
    if "spec" in request:
        machine.copy_from_host(request["spec"], "/tmp/artifacts/spec.ts")
    else:
        machine.succeed("cp /etc/llama-webui-zoo/spec.ts /tmp/artifacts/spec.ts")
    machine.succeed(
        f"echo {shlex.quote(json.dumps(saved_request))} > /tmp/artifacts/request.json"
    )
    if "replay" not in request:
        machine.succeed("python /etc/llama-webui-zoo/smoke.py")
    args = [
        "bombadil",
        "browser",
        "test" if "replay" in request else "fuzz",
        "--headless",
        "--no-sandbox",
        "--output-path",
        "/tmp/artifacts/trace.bin",
        "--width",
        str(options.width),
        "--height",
        str(options.height),
    ]
    if options.chrome_virtual_time_policy:
        args += [
            "--chrome-virtual-time-policy",
            options.chrome_virtual_time_policy,
        ]
    if "replay" in request:
        machine.copy_from_host(request["replay"], "/tmp/input.bin")
        args += ["--reproduce", "/tmp/input.bin"]
    else:
        args += [
            "--time-limit-fuzz",
            f"{options.time_limit_fuzz}s",
            "--time-limit-run",
            f"{options.time_limit_run}s",
            "--parallelism",
            str(options.parallelism),
        ]
        if options.swarm:
            args.append("--swarm")
    args += ["http://127.0.0.1:8080/", "/tmp/artifacts/spec.ts"]
    code, _ = machine.execute(
        shlex.join(args) + " > /tmp/artifacts/bombadil.log 2>&1",
        timeout=options.time_limit_fuzz + options.time_limit_run + 180,
    )
    # Native fuzz can exit successfully despite violations. Inspect the traces.
    machine.succeed(r"""
        set -euo pipefail
        : > /tmp/artifacts/violations
        for trace in /tmp/artifacts/trace*.bin; do
          test -f "$trace" || continue
          bombadil trace --json "$trace" | jq -r --arg trace "$(basename "$trace")" \
            '.metadata.violations[] | "\($trace): \(.name)"' >> /tmp/artifacts/violations
        done
        sort -u -o /tmp/artifacts/violations /tmp/artifacts/violations
    """)
    if code == 0 and machine.succeed("cat /tmp/artifacts/violations").strip():
        code = 2
    machine.succeed(f"echo {code} > /tmp/artifacts/status")
    assert code in (0, 2), machine.succeed("cat /tmp/artifacts/bombadil.log")
    machine.succeed(
        "test -s /tmp/artifacts/trace.bin"
        if "replay" in request
        else "test -s /tmp/artifacts/trace-0.bin"
    )
    if "LLAMA_WEBUI_REQUEST" not in os.environ:
        assert code == 0, machine.succeed("cat /tmp/artifacts/violations")
        machine.succeed("""
            set -euo pipefail
            bombadil trace --json /tmp/artifacts/trace-0.bin | jq -se '
              any(.[]; any(.metadata.snapshots[];
                .name == "page" and .value.ready == true))'
        """)
finally:
    machine.execute("journalctl -u llama-webui --no-pager > /tmp/artifacts/server.log")
    machine.copy_from_machine("/tmp/artifacts")
