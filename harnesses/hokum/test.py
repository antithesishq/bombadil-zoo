import json
import os
import shlex
from pathlib import Path

# Injected by the NixOS test driver, not a standalone Python entry point.
machine = globals()["machine"]

request = json.loads(Path(os.environ["HOKUM_REQUEST"]).read_text())
backend = request.get("backend", "mock")
if backend not in {"mock", "pipewire"}:
    raise ValueError(f"unsupported backend: {backend}")


def seconds(value):
    return int(value[:-1]) * {"s": 1, "m": 60, "h": 3600}[value[-1]]


machine.start()
machine.wait_for_unit("multi-user.target")
machine.succeed(
    "mkdir -m 700 -p /tmp/artifacts /tmp/hokum-bundle; echo 125 > /tmp/artifacts/status"
)
try:
    machine.succeed("install -d -o fuzzer -g users -m 0700 /tmp/hokum-runtime")
    if backend == "pipewire":
        machine.succeed("systemctl start hokum-pipewire")
        machine.wait_for_unit("hokum-pipewire.service")
        machine.wait_until_succeeds("test -S /tmp/hokum-runtime/pipewire-0")
    # Copy from the immutable registered snapshot, never the caller's live files.
    machine.succeed(
        f"cp -r {shlex.quote(request['store_bundle'])}/. /tmp/hokum-bundle/; chmod -R u+w /tmp/hokum-bundle; chown -R fuzzer:users /tmp/hokum-bundle; chown fuzzer:users /tmp/artifacts"
    )
    machine.copy_from_host(os.environ["HOKUM_REQUEST"], "/tmp/artifacts/request.json")
    args = [
        "./bombadil",
        "external",
        "test" if "replay" in request else "fuzz",
        "--specification",
        "/tmp/hokum-bundle/spec.ts",
        "--output-path",
        "/tmp/artifacts/trace.bin",
    ]
    if "replay" in request:
        machine.copy_from_host(request["replay"], "/tmp/input.bin")
        args += ["--reproduce", "/tmp/input.bin"]
    else:
        args += [
            "--time-limit-fuzz",
            request["time_limit_fuzz"],
            "--time-limit-run",
            request["time_limit_run"],
            "--parallelism",
            "1",
        ]
    args += ["--", "./rune-driver", "--log-id", "hokum-target"]
    if backend == "pipewire":
        args += ["--pipewire-runtime", "/tmp/hokum-runtime"]
    args += ["--", "/tmp/hokum-bundle/hokum", "sound"]
    script = """
      set -euo pipefail
      source /etc/hokum-env
      cd /tmp/hokum-bundle
      test ! -S /run/dbus/system_bus_socket
      test ! -d /dev/snd
      test "$DBUS_SESSION_BUS_ADDRESS" = unix:path=/nonexistent-bombadil-bus
      test "$DBUS_SYSTEM_BUS_ADDRESS" = unix:path=/nonexistent-bombadil-bus
      printf 'backend=%s runtime=%s remote=%s; no system bus or sound devices\n' \
        "$HOKUM_BACKEND" "$XDG_RUNTIME_DIR" "$PIPEWIRE_REMOTE" > /tmp/artifacts/isolation.log
    """
    script += f'test "$HOKUM_BACKEND" = {shlex.quote(backend)}\n'
    if backend == "mock":
        script += "test ! -S /tmp/hokum-runtime/pipewire-0\n"
    if backend == "pipewire":
        # Exercise the real protocol from the exact campaign namespace. Require
        # observable service changes, then reset both nodes before bundle controls.
        script += r"""
          exec 3>&1 4>&2
          exec > /tmp/artifacts/pipewire-controls.log 2>&1
          pw-dump > /tmp/artifacts/pw-dump-initial.json
          for side in sink source; do
            if test "$side" = sink; then name=bombadil-output; else name=bombadil-input; fi
            id=$(jq -er --arg name "$name" \
              '[.[] | select(.info.props["node.name"] == $name) | .id] |
               if length == 1 then .[0] else error("missing/duplicate node") end' \
              /tmp/artifacts/pw-dump-initial.json)
            pw-metadata -n default 0 "default.audio.$side" \
              "{\"name\":\"$name\"}" Spa:String:JSON
            pw-cli set-param "$id" Props '{ mute: true, channelVolumes: [ 0.25, 0.25 ] }'
            pw-dump > "/tmp/artifacts/pw-dump-$side-muted.json"
            jq -e --argjson id "$id" \
              '.[] | select(.id == $id) | .info.params.Props[] |
               select(.mute == true and .channelVolumes == [0.25, 0.25])' \
              "/tmp/artifacts/pw-dump-$side-muted.json"
            pw-cli set-param "$id" Props '{ mute: false, channelVolumes: [ 1.0, 1.0 ] }'
            pw-dump > "/tmp/artifacts/pw-dump-$side-reset.json"
            jq -e --argjson id "$id" \
              '.[] | select(.id == $id) | .info.params.Props[] |
               select(.mute == false and .channelVolumes == [1, 1])' \
              "/tmp/artifacts/pw-dump-$side-reset.json"
          done
          pw-dump > /tmp/artifacts/pw-dump-ready.json
          echo 'PipeWire sink/source mute, volume, reset controls passed'
          exec >&3 2>&4
        """
    script += """
      if test -f backend-controls.py; then
        python backend-controls.py > /tmp/artifacts/backend-controls.log 2>&1
      fi
    """ + shlex.join(args)
    # Only the opt-in dedicated audio socket reaches the target, never D-Bus,
    # desktop/user sockets, host audio sockets, or physical devices.
    launch = [
        "systemd-run",
        "--quiet",
        "--wait",
        "--pipe",
        "--collect",
        "--unit=hokum-campaign",
        "--uid=fuzzer",
        "-p",
        "PrivateNetwork=yes",
        "-p",
        "PrivateDevices=yes",
        "-p",
        "InaccessiblePaths=-/run/dbus -/run/user",
        "-p",
        "NoNewPrivileges=yes",
        "bash",
        "-c",
        script,
    ]
    code, _ = machine.execute(
        shlex.join(launch) + " > /tmp/artifacts/bombadil.log 2>&1",
        timeout=seconds(request["time_limit_fuzz"])
        + seconds(request["time_limit_run"])
        + 180,
    )
    machine.succeed(f"echo {code} > /tmp/artifacts/engine-status")
    # A successful engine exit does not prove that properties held.
    machine.succeed("""
      set -euo pipefail
      test ! -s /tmp/hokum-bundle/external-driver-errors.log
      : > /tmp/artifacts/violations
      count=0
      for trace in /tmp/artifacts/trace*.bin; do
        test -f "$trace" || continue
        count=$((count + 1))
        /tmp/hokum-bundle/bombadil trace --json "$trace" > "$trace.json"
        jq -e '.metadata.violations | type == "array"' "$trace.json" >/dev/null
        jq -r --arg trace "$(basename "$trace")" \
          '.metadata.violations[] | "\\($trace): \\(.name)"' "$trace.json" >> /tmp/artifacts/violations
      done
      test "$count" -gt 0
    """)
    violations = machine.succeed("cat /tmp/artifacts/violations").strip()
    status = code if code else (2 if violations else 0)
    machine.succeed(f"echo {status} > /tmp/artifacts/status")
finally:
    if backend == "pipewire":
        machine.execute("""
          source /etc/hokum-env
          timeout 10 pw-dump > /tmp/artifacts/pw-dump-final.json 2> /tmp/artifacts/pw-dump-final.log
          journalctl --no-pager -u hokum-pipewire.service > /tmp/artifacts/pipewire-service.log
          systemctl stop hokum-pipewire
        """)
    machine.execute("""
      mkdir -p /tmp/artifacts/controls
      cd /tmp/hokum-bundle
      find . -type f \\( -name '*.json' -o -name '*.png' -o -name '*.log' \\) \
        -exec cp --parents '{}' /tmp/artifacts/controls/ ';'
    """)
    machine.execute("journalctl --no-pager > /tmp/artifacts/journal.log")
    machine.copy_from_machine("/tmp/artifacts")
