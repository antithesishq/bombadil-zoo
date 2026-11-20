{
  pkgs,
  zoo,
  bombadil,
  ...
}:
let
  version = "0.0.17";
  platform =
    {
      x86_64-linux = "linux-x86_64";
      aarch64-linux = "linux-aarch64";
      aarch64-darwin = "macos-aarch64";
    }
    .${pkgs.stdenv.hostPlatform.system};
  hashes = {
    linux-x86_64 = "78c155d59fa59e42fd56d93037fd75041868c9c67865e8c7f0ca6dcdfac23e75";
    linux-aarch64 = "b4633b8987ec43f1b9454e4629f3b5a4f1e086aae36b84ae4fefeacd6a53761f";
    macos-aarch64 = "5cacb5b3624a79db8fd4e31dcbc59d6a933d7e5ed4c397776d95df6b618296a9";
  };
  fx = pkgs.stdenvNoCC.mkDerivation {
    pname = "vercel-fx";
    inherit version;
    src = pkgs.fetchurl {
      url = "https://github.com/vercel-labs/fx/releases/download/v${version}/fx-${platform}.tar.gz";
      sha256 = hashes.${platform};
    };
    sourceRoot = ".";
    dontStrip = true;
    installPhase = ''
      install -Dm755 fx "$out/bin/fx"
      install -Dm644 LICENSE "$out/share/licenses/fx/LICENSE"
    '';
  };
  # Keep the release binary above as the fuzz target. This separate source
  # build verifies the local zero-width approval and footerless-layout fixes
  # without changing it.
  fxPatched = pkgs.stdenvNoCC.mkDerivation {
    pname = "vercel-fx-patched";
    inherit version;
    src = pkgs.fetchFromGitHub {
      owner = "vercel-labs";
      repo = "fx";
      rev = "d1d4a883382daf8f2e7447dc361978312cf403d2";
      hash = "sha256-zf+Qg0ep4gbmT1d/kPuP6oM6GgbWE/ahnJo69uqaDvk=";
    };
    patches = [
      ./patches/command-approval-zero-width.patch
      ./patches/ask-zero-footer-layout.patch
    ];
    nativeBuildInputs = [ pkgs.zig ];
    dontConfigure = true;
    buildPhase = ''
      runHook preBuild
      export ZIG_GLOBAL_CACHE_DIR="$TMPDIR/zig-global-cache"
      zig build -Doptimize=ReleaseSafe
      runHook postBuild
    '';
    installPhase = ''
      runHook preInstall
      install -Dm755 zig-out/bin/fx "$out/bin/fx"
      install -Dm644 LICENSE "$out/share/licenses/fx/LICENSE"
      runHook postInstall
    '';
  };
  seed = pkgs.runCommand "fx-seed" { } ''
    mkdir -p "$out/home" "$out/project/src"
    printf 'Disposable fx test project.\n' > "$out/project/README.md"
    printf 'print("hello")\n' > "$out/project/src/hello.py"
    touch "$out/project/中文 文件.md" "$out/project/emoji 👩‍💻.txt"
    install -Dm644 ${fxPatched.src}/tests/e2e/fixtures/favicon.png "$out/project/pixel.png"
    install -Dm644 ${fxPatched.src}/tests/e2e/fixtures/placeholder-logo.png "$out/project/placeholder-logo.png"
    printf '\211PNG\r\n\032\n' > "$out/project/truncated.png"
    mkdir -p "$out/project/.agents/skills/zoo-review/references"
    printf '%s\n' '---' 'name: zoo-review' \
      'description: Review fixture changes with Unicode blåbær 中文 👩‍💻 and bounded resources.' '---' \
      '# Fixture review' \"\" 'Read [references/checklist.md](references/checklist.md).' \
      '- Check **input** handling.' '- Preserve `zoo:markdown` fixtures.' 'ZOO_FIXTURE_SKILL' \
      > "$out/project/.agents/skills/zoo-review/SKILL.md"
    printf '%s\n' '# Checklist' \"\" '- Unicode boundaries: blåbær 中文 👩‍💻' \
      '- Narrow tables and wrapped links' 'ZOO_FIXTURE_CHECKLIST' \
      > "$out/project/.agents/skills/zoo-review/references/checklist.md"
  '';
  command = pkgs.writeShellScript "fx-mock" ''
    cd project
    git init -q
    exec ${pkgs.python3}/bin/python ${./mock.py} ${fx}/bin/fx 'zoo:markdown'
  '';
  launch = zoo.launchInCopy {
    name = "fx";
    inherit seed;
    command = "${command}";

    env = {
      HOME = ''"$work/home"'';
      XDG_CONFIG_HOME = ''"$work/home/.config"'';
      XDG_CACHE_HOME = ''"$work/home/.cache"'';
      XDG_DATA_HOME = ''"$work/home/.local/share"'';
      TERM = "xterm-256color";
      PYTHONPATH = "${../../lib}";
      SHELL = "${pkgs.bash}/bin/bash";
      FX_AUTO_UPGRADE = "0";
      FX_SOUND = "0";
      FX_NO_OPEN_BROWSER = "1";
    };
  };
  harness = zoo.sandboxed {
    name = "fx";
    inherit launch;
    inputs = [
      pkgs.gitMinimal
      pkgs.coreutils
    ];
    devShell.packages = [
      fx
      pkgs.python3
    ];
  };
  # Save the selected mode in the spec snapshot, so replay does not depend
  # on the environment variable used to start the campaign.
  stressSpec = pkgs.runCommand "fx-unconstrained-spec" { } ''
    mkdir -p "$out/harnesses/fx" "$out/lib"
    cp -r ${../../lib/spec} "$out/lib/spec"
    sed 's/const unconstrained = false;/const unconstrained = true;/' \
      ${./spec.ts} > "$out/harnesses/fx/spec.ts"
  '';
  smokeSpec = pkgs.writeText "fx-smoke.ts" ''
    import { eventually } from "@antithesishq/bombadil";
    import { extract, weighted } from "@antithesishq/bombadil/terminal";
    export { exitSuccess } from "@antithesishq/bombadil/terminal/defaults/properties";
    const reply = extract((state) => {
      for (let row = 0; row < state.grid.size.rows; row++) {
        if (state.grid.rowText(row).includes("ZOO_MOCK_OK")) return true;
      }
      return false;
    });
    export const mockReply = eventually(() => reply.current).within(5, "seconds");
    export const idle = weighted([[1, { Resize: { columns: 100, rows: 40 } }]]);
  '';
in
pkgs.lib.recursiveUpdate harness {
  packages.vercel-fx = fx;
  packages.vercel-fx-patched = fxPatched;
  legacyPackages.campaigns.fx.run =
    args:
    harness.legacyPackages.campaigns.fx.run (
      (pkgs.lib.optionalAttrs (builtins.getEnv "ZOO_FX_UNCONSTRAINED" == "1") {
        specTree = stressSpec;
      })
      // args
    );
  checks.mock-fx =
    pkgs.runCommand "fx-mock-check"
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
        export SHELL=${pkgs.bash}/bin/bash
        export PYTHONPATH=${../../lib}
        python test.py ${fx}/bin/fx
        mkdir -p home project
        export HOME="$PWD/home" FX_AUTO_UPGRADE=0 FX_SOUND=0
        cd project
        python ${./mock.py} ${fx}/bin/fx ask --json zoo:markdown > reply.json
        python -c 'import json; assert "ZOO_MOCK_OK" in json.load(open("reply.json"))["output"]'
        mkdir -p "$out/stderr"
        ${bombadil.default}/bin/bombadil terminal fuzz \
          --specification ${smokeSpec} --output-path "$out/trace.bin" \
          --time-limit-fuzz 8s --time-limit-run 7s --parallelism 1 \
          -- ${launch} "$out" > "$out/bombadil.log" 2>&1
        if grep -Eq 'mockReply: [0-9]|exitSuccess: [0-9]' "$out/bombadil.log"; then
          cat "$out/bombadil.log"
          exit 1
        fi
        grep -q 'POST /v1/chat/completions' "$out"/stderr/*
      '';
}
