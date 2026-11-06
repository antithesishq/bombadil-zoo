import argparse
import json
import os
from pathlib import Path
import shlex
import time
from typing import Any


def duration(value):
    units = {"s": 1, "m": 60, "h": 3600}
    try:
        seconds = int(value[:-1]) * units[value[-1]]
    except (ValueError, KeyError, IndexError):
        raise argparse.ArgumentTypeError(
            "expected a positive duration such as 30s, 5m or 1h"
        )
    if seconds <= 0:
        raise argparse.ArgumentTypeError("duration must be positive")
    return seconds


request: dict[str, Any] = (
    json.loads(Path(os.environ["HEADPLANE_REQUEST"]).read_text())
    if "HEADPLANE_REQUEST" in os.environ
    else {"args": ["--time-limit-fuzz", "5s", "--time-limit-run", "5s"]}
)
parser = argparse.ArgumentParser()
parser.add_argument("--time-limit-fuzz", type=duration, default=300)
parser.add_argument("--time-limit-run", type=duration, default=30)
options = parser.parse_args(request["args"])


def ready():
    machine.start()
    machine.wait_for_unit("headscale.service")
    machine.wait_until_succeeds("headscale users list -o json", timeout=60)
    machine.wait_for_unit("headplane.service")
    machine.wait_until_succeeds(
        "curl -fsS http://127.0.0.1:3000/admin/login >/dev/null"
    )


def reset():
    machine.succeed(
        "systemctl stop headplane headscale",
        "rm -rf /var/lib/headplane /var/lib/headscale /var/lib/zoo",
        "tar -xpf /tmp/artifacts/fixture.tar -C /",
        "systemctl start headscale headplane",
    )
    ready()


ready()
machine.succeed(
    "mkdir -p /tmp/artifacts/runs /var/lib/zoo; chmod 700 /tmp/artifacts /var/lib/zoo",
    "cp /etc/headplane-zoo/builds.json /tmp/artifacts/builds.json",
    "cp /etc/headplane/config.yaml /tmp/artifacts/headplane.yaml",
)
try:
    if "replay" in request:
        machine.succeed("systemctl stop headplane headscale")
        machine.copy_from_host(request["fixture"], "/tmp/artifacts/fixture.tar")
        machine.copy_from_host(request["spec"], "/tmp/artifacts/spec.ts")
    else:
        for name in ["alice", "bob", "empty-user"]:
            machine.succeed(f"headscale users create {name}")
        for number, (user, name) in enumerate(
            [("alice", "workstation"), ("bob", "build-server")], start=1
        ):
            auth_id = "hskey-authreq-" + str(number) * 24
            machine.succeed(
                f"headscale debug create-node --user {user} --name {name} --key {auth_id}",
                f"headscale auth register --user {user} --auth-id {auth_id}",
            )
        machine.succeed(
            "headscale apikeys create --expiration 365d > /var/lib/zoo/api-key",
            "headscale preauthkeys -u 1 create --reusable --expiration 24h",
            "headscale preauthkeys -u 2 create --expiration 1h",
            "headscale nodes expire --identifier 2",
            """printf '%s' '{"acls":[{"action":"accept","src":["*"],"dst":["*:*"]}]}' > /var/lib/zoo/policy.json""",
            "headscale policy set --file /var/lib/zoo/policy.json",
        )
        # Capture quiescent databases, not SQLite files while services write them.
        machine.succeed(
            "systemctl stop headplane headscale",
            "tar -cpf /tmp/artifacts/fixture.tar -C / var/lib/headscale var/lib/headplane var/lib/zoo",
            "systemctl start headscale headplane",
        )
        ready()
        if "spec" in request:
            machine.copy_from_host(request["spec"], "/tmp/artifacts/spec.ts")
        else:
            machine.succeed("cp /etc/headplane-zoo/spec.ts /tmp/artifacts/spec.ts")
        machine.succeed(
            "python - <<'PY'\nfrom pathlib import Path\np = Path('/tmp/artifacts/spec.ts')\np.write_text(p.read_text().replace('__HEADPLANE_API_KEY__', Path('/var/lib/zoo/api-key').read_text().strip()))\nPY"
        )
        machine.succeed("python /etc/headplane-zoo/smoke.py")
        users = json.loads(machine.succeed("headscale users list -o json"))
        assert any(user["name"] == "smoke-created" for user in users)

    status = 0
    deadline = time.monotonic() + options.time_limit_fuzz
    run_id = 0
    while run_id == 0 or ("replay" not in request and time.monotonic() < deadline):
        reset()
        users = json.loads(machine.succeed("headscale users list -o json"))
        assert [user["name"] for user in users] == ["alice", "bob", "empty-user"]
        output = f"/tmp/artifacts/runs/{run_id}"
        machine.succeed(f"mkdir -p {output}")
        if "replay" in request:
            viewport = json.loads(
                (Path(request["replay"]) / "viewport.json").read_text()
            )
        else:
            width, height = [(1280, 800), (800, 600), (1440, 900)][run_id % 3]
            viewport = {"width": width, "height": height}
        machine.succeed(
            f"echo {shlex.quote(json.dumps(viewport))} > {output}/viewport.json"
        )
        args = [
            "bombadil",
            "browser",
            "test",
            "--headless",
            "--no-sandbox",
            "--output-path",
            output,
            "--width",
            str(viewport["width"]),
            "--height",
            str(viewport["height"]),
        ]
        if "replay" in request:
            machine.copy_from_host(
                str(Path(request["replay"]) / "trace.jsonl"), "/tmp/replay/trace.jsonl"
            )
            args += ["--reproduce", "/tmp/replay"]
        else:
            seconds = min(
                options.time_limit_run, max(1, int(deadline - time.monotonic()))
            )
            args += ["--time-limit", f"{seconds}s", "--exit-on-violation"]
        args += ["http://127.0.0.1:3000/admin/", "/tmp/artifacts/spec.ts"]
        code, _ = machine.execute(
            shlex.join(args) + f" > /tmp/artifacts/bombadil-{run_id}.log 2>&1",
            timeout=3600 if "replay" in request else int(options.time_limit_run) + 180,
        )
        machine.succeed(f"echo {code} > /tmp/artifacts/runs/{run_id}/status")
        machine.succeed(
            f"journalctl -u headplane -u headscale --no-pager > /tmp/artifacts/services-{run_id}.log"
        )
        if code:
            status = code
            break
        run_id += 1
        if "replay" in request:
            break
    machine.succeed(f"echo {status} > /tmp/artifacts/status")
    assert status in (0, 2), machine.succeed(
        f"cat /tmp/artifacts/bombadil-{run_id}.log"
    )
    if "HEADPLANE_REQUEST" not in os.environ:
        assert status == 0, "property violation in smoke campaign"
finally:
    machine.execute(
        "journalctl -u headplane -u headscale --no-pager > /tmp/artifacts/services.log"
    )
    machine.copy_from_machine("/tmp/artifacts")
