{
  pkgs,
  zoo,
  bombadil,
  ...
}:
let
  system = pkgs.stdenv.hostPlatform.system;
  # 1.0.77 is the stable channel (https://x.ai/cli/stable). Campaigns are
  # impure builds, so ZOO_GROK_VERSION=1.0.87 selects the alpha channel
  # (https://x.ai/cli/alpha) to check whether a finding is already fixed.
  requested = builtins.getEnv "ZOO_GROK_VERSION";
  version = if requested == "" then "1.0.77" else requested;
  hashes = {
    # Homebrew/homebrew-cask#300355; checked against the vendor downloads.
    "1.0.77" = {
      x86_64-linux = "sha256-twKVCqWCfYVeSTJ4q2IVpOD1vOtbumxiQ6n1XN0UOwo=";
      aarch64-linux = "sha256-sw7uFKZWEk7zydqFd7Xng+8s/6vrK2ecXEljPnfu1XQ=";
      aarch64-darwin = "sha256-GXxmpj5axG4HRQsMoh0UHOZlBQpBIYDxhdrfrhx6Wyo=";
    };
    # Vendor download, fetched 2026-11-14.
    "1.0.87".x86_64-linux = "sha256-uOYmQcvxO/I1HC39e4tgmoAiU+D17CBMyGFWXPBSR8o=";
  };
  # The nixpkgs release is a vendor binary. Allow only this package's license.
  grok =
    (import pkgs.path {
      inherit system;
      config.allowUnfreePredicate = p: (p.pname or "") == "grok-build";
    }).grok-build.overrideAttrs
      (_: {
        inherit version;
        src = pkgs.fetchurl {
          url = "https://x.ai/cli/grok-${version}-${
            {
              x86_64-linux = "linux-x86_64";
              aarch64-linux = "linux-aarch64";
              aarch64-darwin = "macos-aarch64";
            }
            .${system}
          }";
          hash = hashes.${version}.${system};
        };
      });
  seed = pkgs.runCommand "grok-build-seed" { } ''
    mkdir -p "$out/project" "$out/home"
    printf 'A disposable project for the Grok TUI campaign.\n' > "$out/project/README.md"
    printf 'print("hello")\n' > "$out/project/hello.py"
    # File-reference completion and directory listings: wide and combining
    # characters, spaces, a name near the length limit, depth, and volume.
    cd "$out/project"
    touch -- '中文 文件.md' 'emoji 👩‍💻.txt' 'é combining.txt' '-dash.txt' 'sp ace  two.txt' \
      "$(printf 'long-%0200d.txt' 0)" '.hidden' 'UPPER.TXT' 'a.b.c.d.e'
    mkdir -p deep/a/b/c/d/e/f/g/h/i/j many 'dir 中文'
    touch deep/a/b/c/d/e/f/g/h/i/j/leaf.rs 'dir 中文/inner.py'
    for i in $(seq 1 400); do touch "many/file-$i.txt"; done
    head -c 4096 /dev/urandom > binary.bin
    seq 1 20000 > big.txt
    printf '# Rules\n\nUse zoo fixtures.\n' > AGENTS.md
  '';
  command = pkgs.writeShellScript "grok-build-mock" ''
    cd project
    # A repository with one commit and one uncommitted change, for the git
    # status line, diffs, /fork, and worktree dialogs.
    {
      git init -q . &&
        git -c user.name=zoo -c user.email=zoo@example.invalid add -A &&
        git -c user.name=zoo -c user.email=zoo@example.invalid commit -qm seed &&
        echo 'print("changed")' >> hello.py
    } >/dev/null 2>&1 || true
    exec ${pkgs.python3}/bin/python ${./mock.py} \
      ${grok}/bin/grok --trust --fullscreen --disable-web-search --no-subagents \
      -m zoo-mock 'zoo:markdown'
  '';
  launch = zoo.launchInCopy {
    name = "grok-build";
    inherit seed;
    command = "${command}";
    env = {
      HOME = ''"$work/home"'';
      XDG_CONFIG_HOME = ''"$work/home/.config"'';
      XDG_CACHE_HOME = ''"$work/home/.cache"'';
      XDG_DATA_HOME = ''"$work/home/.local/share"'';
      TERM = "xterm-256color";
      RUST_BACKTRACE = "full";
    };
  };
in
pkgs.lib.recursiveUpdate
  (zoo.sandboxed {
    name = "grok-build";
    inherit launch;
    inputs = [
      pkgs.gitMinimal
      pkgs.coreutils
      pkgs.ripgrep
    ];
    devShell.packages = [
      grok
      pkgs.python3
    ];
  })
  {
    packages.grok-build = grok;
    checks.mock-grok-build =
      let
        smokeSpec = pkgs.writeText "grok-build-smoke.ts" ''
          import { eventually } from "@antithesishq/bombadil";
          import { extract, weighted } from "@antithesishq/bombadil/terminal";
          export { exitSuccess } from "@antithesishq/bombadil/terminal/defaults/properties";
          const reply = extract((state) => {
            for (let i = 0; i < state.grid.size.rows; i++) {
              if (state.grid.rowText(i).includes("ZOO_MOCK_OK")) return true;
            }
            return false;
          });
          export const mockReply = eventually(() => reply.current).within(5, "seconds");
          export const idle = weighted([[1, { Resize: { columns: 100, rows: 40 } }]]);
        '';
      in
      pkgs.runCommand "grok-build-mock-check"
        {
          nativeBuildInputs = [
            pkgs.python3
            pkgs.gitMinimal
            pkgs.coreutils
          ];
        }
        ''
          cp ${./test.py} test.py
          cp ${./mock.py} mock.py
          python test.py
          mkdir -p "$out/stderr"
          ${bombadil.default}/bin/bombadil terminal fuzz \
            --specification ${smokeSpec} --output-path "$out/trace.bin" \
            --time-limit-fuzz 8s --time-limit-run 7s --parallelism 1 \
            -- ${launch} "$out" > "$out/bombadil.log" 2>&1 \
            || { cat "$out/bombadil.log"; exit 1; }
          if grep -Eq 'mockReply: [0-9]|exitSuccess: [0-9]' "$out/bombadil.log"; then
            tail -5 "$out/bombadil.log"
            # The last screens show what the target displayed instead.
            for trace in "$out"/trace-*.bin; do
              ${bombadil.default}/bin/bombadil trace --screen "$trace" | tail -60
            done
            exit 1
          fi
          grep -q 'scenario=markdown stream=True model=zoo-mock' "$out"/stderr/* \
            || { cat "$out/bombadil.log" "$out"/stderr/*; exit 1; }
        '';
  }
