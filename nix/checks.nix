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
    mkdir -p "$out"
    cp -r ${shrinkSpec} "$out/spec"
    # Binary trace v1: terminal envelope, nine metadata records, end record.
    ${pkgs.python3}/bin/python - <<'PY' | ${pkgs.zstd}/bin/zstd -q > "$out/trace.bin.zst"
    import json
    import struct
    import sys
    import zlib

    def checked(data):
        return data + struct.pack("<I", zlib.crc32(data))

    def record(tag, payload):
        sys.stdout.buffer.write(checked(struct.pack("<HHI", tag, 0, len(payload))))
        sys.stdout.buffer.write(struct.pack("<I", zlib.crc32(payload)) + payload)

    sys.stdout.buffer.write(checked(struct.pack("<8sHH", b"BMBDTRC\0", 1, 1)))
    for i, key in enumerate("aaaaaaaax"):
        record(1, json.dumps({
            "timestamp": i,
            "action": {"TypeText": {"text": key}},
            "state": {"scroll_offset": 0, "exit_status": None, "cursor": {
                "position": {"column": 0, "row": 0}, "visible": True,
                "blinking": False, "visual_style": "Block", "color": "None"
            }},
            "snapshots": [],
            "violations": [{"name": "neverBroken", "violation": {"False": {
                "time": i, "condition": "!broken.current", "snapshots": []
            }}}] if key == "x" else []
        }).encode())
    record(5, b"")
    PY
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
    trace = "${shrinkInput}/trace.bin.zst";
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
    ${bombadil.default}/bin/bombadil trace --json ${shrunk}/trace.bin \
      | jq -se '([.[] | select(.metadata.action != null)] | length) == 1 and
        any(.[]; any(.metadata.violations[]; .name == "neverBroken"))'
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
