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
    model = pkgs.fetchurl {
      url = "https://huggingface.co/ggml-org/test-model-stories260K/resolve/479896ec924af6d40fd419ab8f4d1eb2101de00d/stories260K-f32.gguf";
      hash = "sha256-Jwy6G9UQn0LQM1D2BAYCRWBGTbFzwOOH2R8EJtO9JW0=";
    };
    vm = pkgs.testers.runNixOSTest {
      name = "llama-webui";
      nodes.machine = import ./vm.nix { inherit pkgs bombadil model; };
      testScript = builtins.readFile ./test.py;
      globalTimeout = 3600;
    };
    app =
      mode:
      pkgs.writeShellApplication {
        name = "${mode}-llama-webui";
        runtimeInputs = [
          pkgs.coreutils
          pkgs.gitMinimal
          pkgs.jq
        ];
        text = ''
          if [ "''${1:-}" = --help ]; then
            echo 'usage: ${mode}-llama-webui ${
              if mode == "fuzz" then
                "[--time-limit-fuzz 5m] [--time-limit-run 20s] [--parallelism 1] [--swarm] [--width 1280] [--height 800] [--chrome-virtual-time-policy POLICY] (virtual time default: PauseIfNetworkFetchesPending)"
              else
                "<campaign-directory>/artifacts/trace-<id>.bin"
            }'
            exit 0
          fi
          root="$(git rev-parse --show-toplevel)"
          mkdir -p "$root/.state/llama-webui"
          run="$(mktemp -d "$root/.state/llama-webui/${mode}-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
          chmod 700 "$run"
          ${
            if mode == "fuzz" then
              ''
                driver=${vm.driver}/bin/nixos-test-driver
                cp ${./spec.ts} "$run/spec.ts"
                jq -n --arg spec "$run/spec.ts" --args '$ARGS.named + {args: $ARGS.positional}' -- "$@" > "$run/request.json"
              ''
            else
              ''
                if [ "$#" -ne 1 ]; then
                  echo 'expected one binary trace file' >&2
                  exit 1
                fi
                trace="$(realpath "$1")"
                campaign="$(dirname "$trace")"
                test -f "$trace"
                driver="$(cat "$campaign/driver")"
                test -x "$driver"
                jq --arg replay "$trace" --arg spec "$campaign/spec.ts" \
                  '. + {replay: $replay, spec: $spec}' "$campaign/request.json" > "$run/request.json"
              ''
          }
          export LLAMA_WEBUI_REQUEST="$run/request.json"
          runtime="$(mktemp -d "''${XDG_RUNTIME_DIR:-''${TMPDIR:-/tmp}}/llama-webui-XXXXXX")"
          trap 'rm -rf "$runtime"' EXIT
          export XDG_RUNTIME_DIR="$runtime"
          nix-store --add-root "$run/driver-build" --indirect \
            --realise "$(dirname "$(dirname "$driver")")" >/dev/null
          echo '${mode}-llama-webui: writing to '"$run" >&2
          status=0
          "$driver" -o "$run" 2>&1 | tee "$run/driver.log" || status=$?
          if [ -d "$run/artifacts" ]; then
            printf '%s\n' "$driver" > "$run/artifacts/driver"
          fi
          if [ "$status" -ne 0 ]; then exit "$status"; fi
          exit "$(cat "$run/artifacts/status")"
        '';
      };
  in
  {
    packages.llama-webui-vm = vm.driver;
    apps = {
      fuzz-llama-webui = zoo.app (app "fuzz");
      reproduce-llama-webui = zoo.app (app "reproduce");
    };
    checks.smoke-llama-webui = vm;
    devShell = pkgs.mkShell {
      packages = [
        bombadil.default
        pkgs.llama-cpp
        pkgs.chromium
      ];
    };
  }
