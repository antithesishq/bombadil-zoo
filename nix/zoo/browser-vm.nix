# A browser harness in a disposable, offline NixOS VM. The runner owns app and
# replay behavior, virtual-time persistence and artifacts; harnesses supply the
# target service, fixture preparation, smoke test and browser specification.
{
  pkgs,
  bombadil,
  scripts,
}:
{
  name,
  target,
  origin,
  healthCheck,
  serviceUnits ? [ "${name}.service" ],
  coverage,
  virtualTimePolicy ? "PauseIfNetworkFetchesPending",
  prepare ? null,
  extraPackages ? [ ],
  devShell ? { },
}:
if !pkgs.stdenv.hostPlatform.isLinux then
  { devShell = pkgs.mkShell { }; }
else
  let
    inherit (pkgs) lib;
    harness = ../../harnesses + "/${name}";
    config = {
      inherit
        name
        origin
        healthCheck
        serviceUnits
        coverage
        virtualTimePolicy
        ;
    };
    prepareScript = if prepare == null then "def prepare():\n    pass\n" else builtins.readFile prepare;
    vm = pkgs.testers.runNixOSTest {
      inherit name;
      nodes.machine =
        { ... }:
        {
          imports = [
            (import (harness + "/vm.nix") { inherit pkgs bombadil; })
            {
              # Two vCPUs support the server and two browser workers without
              # letting a VM consume the host's whole processor budget.
              virtualisation = {
                memorySize = 4096;
                cores = 2;
                diskSize = 4096;
                restrictNetwork = true;
              };
              environment.systemPackages = [
                bombadil.default
                target
                pkgs.chromium
                pkgs.curl
                pkgs.jq
                (pkgs.python3.withPackages (p: [ p.playwright ]))
              ]
              ++ extraPackages;
              environment.etc = {
                "zoo-browser/spec.ts".source = harness + "/spec.ts";
                "zoo-browser/smoke.py".source = harness + "/smoke.py";
                "zoo-browser/builds.json".text = builtins.toJSON {
                  "${name}" = toString target;
                  "${name}Version" = target.version or "";
                  chromium = toString pkgs.chromium;
                  chromiumVersion = pkgs.chromium.version;
                  bombadil = toString bombadil.default;
                };
              };
            }
          ];
        };
      testScript = ''
        import json
        zoo = json.loads(${builtins.toJSON (builtins.toJSON config)})
        ${prepareScript}
        ${builtins.readFile ./browser-vm.py}
      '';
      globalTimeout = 3600;
    };
    app =
      mode:
      pkgs.writeShellApplication {
        name = "${mode}-${name}";
        runtimeInputs = [
          pkgs.coreutils
          pkgs.gitMinimal
          pkgs.jq
        ];
        text = ''
          if [ "''${1:-}" = --help ]; then
            echo 'usage: ${mode}-${name} ${
              if mode == "fuzz" then
                "[--time-limit-fuzz 5m] [--time-limit-run 20s] [--parallelism 1] [--swarm] [--width 1280] [--height 800] [--chrome-virtual-time-policy POLICY] (default: ${virtualTimePolicy})"
              else
                "<campaign-directory>/artifacts/trace-<id>.bin"
            }'
            exit 0
          fi
          ${scripts.findRoot}
          mkdir -p "$root/.state/${name}"
          run="$(mktemp -d "$root/.state/${name}/${mode}-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
          chmod 700 "$run"
          ${
            if mode == "fuzz" then
              ''
                driver=${vm.driver}/bin/nixos-test-driver
                cp ${harness + "/spec.ts"} "$run/spec.ts"
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
          export ZOO_BROWSER_REQUEST="$run/request.json"
          runtime="$(mktemp -d "''${XDG_RUNTIME_DIR:-''${TMPDIR:-/tmp}}/${name}-XXXXXX")"
          trap 'rm -rf "$runtime"' EXIT
          export XDG_RUNTIME_DIR="$runtime"
          nix-store --add-root "$run/driver-build" --indirect \
            --realise "$(dirname "$(dirname "$driver")")" >/dev/null
          echo '${mode}-${name}: writing to '"$run" >&2
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
    packages."${name}-vm" = vm.driver;
    apps = {
      "fuzz-${name}" = scripts.app (app "fuzz");
      "reproduce-${name}" = scripts.app (app "reproduce");
    };
    checks."smoke-${name}" = vm;
    devShell = pkgs.mkShell (
      devShell
      // {
        packages = [
          bombadil.default
          target
          pkgs.chromium
        ]
        ++ extraPackages
        ++ (devShell.packages or [ ]);
      }
    );
  }
