# Checks that aren't specific to one harness.
{ pkgs, bombadil }:
let
  inherit (pkgs) lib;
  shrinkSpec = pkgs.writeTextDir "harnesses/ncdu/spec.ts" ''
    import { always } from "@antithesishq/bombadil";
    import { CharSet } from "@antithesishq/bombadil/actions";
    import { extract } from "@antithesishq/bombadil/terminal";
    import { typeFromSet } from "@antithesishq/bombadil/terminal/defaults/actions";
    const broken = extract((state) => state.grid.rowText(0).includes("broken"));
    export const neverBroken = always(() => !broken.current);
    export const type = typeFromSet(CharSet.fromLiterals("a", "x"));
  '';
  shrinkInput = pkgs.runCommand "shrink-input" { } ''
    mkdir -p "$out/runs/0"
    cp -r ${shrinkSpec} "$out/spec"
    {
      for i in $(seq 1 8); do
        echo '{"action":{"TypeText":{"text":"a"}},"violations":[]}'
      done
      echo '{"action":{"TypeText":{"text":"x"}},"violations":[{"name":"neverBroken"}]}'
    } | ${pkgs.zstd}/bin/zstd -q > "$out/runs/0/trace.jsonl.zst"
  '';
  shrinkHarness = (import ./zoo { inherit pkgs bombadil; }).sandboxed {
    name = "ncdu";
    launch = pkgs.writeShellScript "shrink-target" ''
      ${pkgs.coreutils}/bin/stty -echo -icanon
      while IFS= read -r -n 1 key; do
        if [ "$key" = x ]; then printf '\rbroken'; fi
      done
    '';
  };
  shrunk = shrinkHarness.legacyPackages.campaigns.ncdu.shrink {
    trace = "${shrinkInput}/runs/0/trace.jsonl.zst";
    specTree = shrinkSpec;
    args = [
      "--property"
      "neverBroken"
      "--time-limit"
      "30s"
      "--parallelism"
      "2"
    ];
  };
in
{
  # A noisy nine-action failure reduces to the one required keystroke.
  # This exercises compressed input, a saved spec, option forwarding and
  # the real shrinker/target through the sandboxed runner's public interface.
  shrink = pkgs.runCommand "shrink-harness" { nativeBuildInputs = [ pkgs.jq ]; } ''
    test "$(cat ${shrunk}/status)" = 0 || { cat ${shrunk}/bombadil.log; exit 1; }
    test -f ${shrunk}/spec/harnesses/ncdu/spec.ts
    jq -se '([.[] | select(.action != null)] | length) == 1 and
      any(.[]; any(.violations[]; .name == "neverBroken"))' \
      ${shrunk}/runs/0/trace.jsonl
    touch "$out"
  '';

  # Type-checks the shared spec helpers and every harness's spec against the
  # Bombadil package's type definitions.
  specs =
    pkgs.runCommand "specs"
      {
        src = lib.fileset.toSource {
          root = ../.;
          fileset = lib.fileset.unions [
            ../tsconfig.json
            ../lib/spec
            (lib.fileset.fileFilter (f: f.name == "spec.ts") ../harnesses)
          ];
        };
      }
      ''
        cp -r $src/. . && chmod -R u+w .
        mkdir -p node_modules/@antithesishq
        ln -s ${bombadil.npm-package} node_modules/@antithesishq/bombadil
        ${pkgs.typescript}/bin/tsc -p tsconfig.json
        touch $out
      '';
}
