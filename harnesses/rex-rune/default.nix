{
  pkgs,
  zoo,
  rex-rune,
  bombadil-drivers,
  bombadil-external,
}:
if pkgs.stdenv.hostPlatform.system != "x86_64-linux" then
  { devShell = pkgs.mkShell { }; }
else
  let
    system = pkgs.stdenv.hostPlatform.system;
    # Opt in to one host-installed package, never its profile or configuration.
    serverPath = builtins.getEnv "ZOO_REX_PACKAGE";
    server =
      if
        builtins.match "/nix/store/[a-z0-9]{32}-[^/]+" serverPath != null
        && builtins.pathExists "${serverPath}/bin/rex"
      then
        builtins.storePath serverPath
      else
        throw "Rex must already be installed: set ZOO_REX_PACKAGE to its Nix store package (see harnesses/rex-rune/README.md).";
    rexPkgs = import rex-rune.inputs.nixpkgs {
      inherit system;
      overlays = [ bombadil-external.inputs.rust-overlay.overlays.default ];
    };
    # Match Rex's mise.toml, including its lint tools, rather than nixpkgs' newer Rust.
    toolchain = rexPkgs.rust-bin.stable."1.96.1".default;
    source = pkgs.applyPatches {
      name = "rex-rune-bombadil-source";
      src = rex-rune;
      patches = [ ./bombadil.patch ];
    };
    driverSource = builtins.path {
      path = bombadil-drivers + "/drivers/rune";
      name = "bombadil-rune-source";
    };
    target =
      (rex-rune.packages.${system}.default.override {
        rustPlatform = rexPkgs.makeRustPlatform {
          cargo = toolchain;
          rustc = toolchain;
        };
        pkgs = rexPkgs // {
          clippy = toolchain;
          rustfmt = toolchain;
        };
      }).overrideAttrs
        (old: {
          pname = "rex-rune-bombadil";
          src = source;
          cargoDeps = pkgs.rustPlatform.importCargoLock {
            lockFile = "${source}/Cargo.lock";
            outputHashes."rune-kit-0.0.1" = "sha256-IWvwANCYSmgeI9ZZ/X0YYFeJaSKSr2CYnQSsZyJgB1c=";
          };
          postPatch = (old.postPatch or "") + ''
            cp -r ${driverSource} bombadil-driver
            chmod -R u+w bombadil-driver
          '';
          cargoBuildFlags = old.cargoBuildFlags ++ [
            "--features"
            "bombadil"
          ];
        });
    # This experimental engine branch predates the agreed apply_action spelling.
    # Correct its wire tag at the source, without retaining the stale protocol.
    engine = bombadil-external.packages.${system}.default.overrideAttrs (old: {
      postPatch = (old.postPatch or "") + ''
        substituteInPlace lib/bombadil-rpc/src/protocol.rs \
          --replace-fail '    Apply { action: json::Value },' \
          '    #[serde(rename = "apply_action")] Apply { action: json::Value },'
      '';
      cargoExtraArgs = "-p bombadil-cli --no-default-features --features external";
    });
    launch =
      (pkgs.writeShellApplication {
        name = "launch-rex-rune";
        runtimeInputs = [
          pkgs.coreutils
          pkgs.bashInteractive
          server
        ];
        text = ''
          run="$1"
          log_prefix="''${BOMBADIL_RUN_ID:-unknown}-$$"
          session="$(mktemp -d)"
          export HOME="$session/home"
          export XDG_CONFIG_HOME="$HOME/.config"
          export XDG_CACHE_HOME="$HOME/.cache"
          export XDG_DATA_HOME="$HOME/.local/share"
          export XDG_RUNTIME_DIR="$session/runtime"
          mkdir -p "$HOME" "$XDG_RUNTIME_DIR" "$run/stderr"
          chmod 700 "$XDG_RUNTIME_DIR"
          export REX_BOMBADIL=1 REX_LINUX_NO_UPDATE_CHECK=1
          export VK_DRIVER_FILES=${pkgs.mesa}/share/vulkan/icd.d/lvp_icd.x86_64.json
          export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
          export SHELL=${pkgs.bashInteractive}/bin/bash
          export REX_SERVER="unix://$session/server.sock"
          ${server}/bin/rex server run --listen "$REX_SERVER" \
            --state-dir "$session/server-state" --restore=false \
            --config /dev/null > "$run/stderr/$log_prefix-server" 2>&1 &
          server_pid=$!
          cleanup() {
            kill "$server_pid" 2>/dev/null || true
            wait "$server_pid" 2>/dev/null || true
            rm -rf "$session"
          }
          trap cleanup EXIT
          for _ in $(seq 1 100); do
            if [ -S "$session/server.sock" ]; then break; fi
            if ! kill -0 "$server_pid" 2>/dev/null; then
              cat "$run/stderr/$log_prefix-server" >&2
              exit 1
            fi
            sleep 0.05
          done
          # Seed a real terminal; all later UI-created sessions use the same private server.
          ${server}/bin/rex --autostart=false --server "$REX_SERVER" new "Zoo sandbox" \
            --cwd "$HOME" -- "$SHELL" --noprofile --norc > "$run/stderr/$log_prefix-session" 2>&1
          printf '{"hosts":[{"label":"Zoo sandbox","endpoint":"%s","shell":"%s"}]}\n' \
            "$REX_SERVER" "$SHELL" > "$session/workspace.json"
          ${target}/bin/rex-linux \
            --config "$session/workspace.json" --endpoint "$REX_SERVER" --session "Zoo sandbox" \
            --window-size 1000x700 2> "$run/stderr/$log_prefix"
        '';
      }).overrideAttrs
        {
          preferLocalBuild = true;
          allowSubstitutes = false;
        };
    harness = zoo.sandboxed {
      name = "rex-rune";
      interface = "external";
      localOnly = true;
      inherit engine;
      launch = pkgs.lib.getExe launch;
    };
  in
  harness
  // {
    packages = {
      rex-rune = target;
      bombadil-external = engine;
    };
    checks = harness.checks // {
      rex-rune-protocol =
        pkgs.runCommand "rex-rune-protocol"
          {
            preferLocalBuild = true;
            allowSubstitutes = false;
            nativeBuildInputs = [
              pkgs.jq
              pkgs.coreutils
            ];
          }
          ''
            mkdir -p "$out"
            {
              # Advance real poll hooks while the private server's terminal stream connects.
              for _ in $(seq 1 40); do
                sleep 0.05
                printf '%s\n' '{"type":"apply_action","action":{"Key":{"name":"Escape"}}}'
              done
              printf '%s\n' \
                '{"type":"apply_action","action":{"Tap":{"key":"settings"}}}' \
                '{"type":"terminate"}'
            } \
              | timeout 60 ${launch}/bin/launch-rex-rune "$out" > "$out/messages.jsonl"
            jq -se '
              .[0].type == "hello" and .[0].protocol == 0 and
              (map(select(.type == "state")) |
                any(.state.elements | any(.key // "" | startswith("grid:"))) and
                (last.state.elements | any(.key == "close-settings")) and
                all(.settled == false and (.screenshot_png | length > 0)))
            ' "$out/messages.jsonl"
            jq -sr 'map(select(.type == "state")) | .[-2].screenshot_png' \
              "$out/messages.jsonl" | base64 -d > "$out/default.png"
            jq -sr 'map(select(.type == "state")) | last.screenshot_png' \
              "$out/messages.jsonl" | base64 -d > "$out/settings.png"
          '';
    };
    devShell = pkgs.mkShell {
      packages = [
        target
        pkgs.jq
      ];
    };
  }
