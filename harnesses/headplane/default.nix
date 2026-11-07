{
  pkgs,
  bombadil,
  zoo,
}:
if !pkgs.stdenv.hostPlatform.isLinux then
  { devShell = pkgs.mkShell { }; }
else
  let
    inherit (pkgs) lib;
    vm = pkgs.testers.runNixOSTest {
      name = "headplane";
      nodes.machine = import ./vm.nix { inherit pkgs bombadil; };
      testScript = builtins.readFile ./test.py;
      # The same driver is also used for longer, user-requested campaigns.
      globalTimeout = 3600;
    };

    app =
      {
        mode,
        usage,
        prepare,
      }:
      pkgs.writeShellApplication {
        name = "${mode}-headplane";
        runtimeInputs = [
          pkgs.coreutils
          pkgs.gitMinimal
          pkgs.jq
        ];
        text = ''
          usage=${lib.escapeShellArg "usage: ${mode}-headplane ${usage}"}
          if [ "''${1:-}" = --help ]; then
            echo "$usage"
            exit 0
          fi
          root="$(git rev-parse --show-toplevel)"
          mkdir -p "$root/.state/headplane"
          run="$(mktemp -d "$root/.state/headplane/${mode}-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
          chmod 700 "$run"
          ${prepare}
          echo "${mode}-headplane: writing to $run" >&2
          export HEADPLANE_REQUEST="$run/request.json"
          # The driver otherwise reuses vm-state-machine and shared-xchg across
          # invocations. Keep this path short enough for QEMU's Unix sockets.
          runtime="$(mktemp -d "''${XDG_RUNTIME_DIR:-''${TMPDIR:-/tmp}}/headplane-XXXXXX")"
          trap 'rm -rf "$runtime"' EXIT
          export XDG_RUNTIME_DIR="$runtime"
          # Keep the original VM, browser and target builds available for replay.
          nix-store --add-root "$run/driver-build" --indirect \
            --realise "$(dirname "$(dirname "$driver")")" >/dev/null
          status=0
          "$driver" -o "$run" 2>&1 | tee "$run/driver.log" || status=$?
          if [ -d "$run/artifacts" ]; then
            printf '%s\n' "$driver" > "$run/artifacts/driver"
          fi
          if [ "$status" -ne 0 ]; then
            exit "$status"
          fi
          exit "$(cat "$run/artifacts/status")"
        '';
      };
    fuzz = app {
      mode = "fuzz";
      usage = "[--time-limit-fuzz 5m] [--time-limit-run 30s]";
      prepare = ''
        driver=${vm.driver}/bin/nixos-test-driver
        cp ${./spec.ts} "$run/spec.ts"
        jq -n --arg spec "$run/spec.ts" --args '$ARGS.named + {args: $ARGS.positional}' -- "$@" > "$run/request.json"
      '';
    };
    reproduce = app {
      mode = "reproduce";
      usage = "<campaign-directory>/artifacts/runs/<id>";
      prepare = ''
        if [ "$#" -ne 1 ]; then
          echo "$usage" >&2
          exit 1
        fi
        trace="$(realpath "$1")"
        campaign="$(dirname "$(dirname "$trace")")"
        test -f "$trace/trace.bin"
        test -f "$campaign/fixture.tar"
        driver="$(cat "$campaign/driver")"
        test -x "$driver"
        jq -n --arg replay "$trace" --arg fixture "$campaign/fixture.tar" \
          --arg spec "$campaign/spec.ts" '$ARGS.named + {args: []}' > "$run/request.json"
      '';
    };
  in
  {
    packages.headplane-vm = vm.driver;
    apps = {
      fuzz-headplane = zoo.app fuzz;
      reproduce-headplane = zoo.app reproduce;
    };
    checks.smoke-headplane = vm;
    devShell = pkgs.mkShell {
      packages = [
        bombadil.default
        pkgs.chromium
      ];
    };
  }
