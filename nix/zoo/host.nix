# A harness whose campaigns run on your machine, for targets that need real
# resources, e.g. a Kubernetes cluster.
#
#   name        the harness directory under harnesses/
#   launch      script: launch <run dir>
#   setup       shell run first in both apps, with $state set to
#               .state/<name>; use it to isolate the target
#   crashLines  regex for crash lines on stderr
{
  pkgs,
  bombadil,
  scripts,
}:
{
  name,
  launch,
  setup ? "",
  crashLines ? scripts.defaultCrashLines,
}:
let
  inherit (pkgs) lib;
  inherit (scripts) finalize report specIn;

  # Sets up the target and a fresh run directory under .state/<name>/<$1>.
  prelude = ''
    ${scripts.findRoot}
    state="$root/.state/${name}"
    mkdir -p "$state"
    ${setup}
    run="$state/$1/$(date +%Y%m%d-%H%M%S)"
    shift
    mkdir -p "$run/stderr"
  '';

  finish = kind: ''
    echo "$status" > "$run/status"
    ${finalize}/bin/zoo-finalize "$run" ${lib.escapeShellArg crashLines}
    ${report}/bin/zoo-report "$run" "${kind}-${name}"
  '';

  fuzz = pkgs.writeShellApplication {
    name = "fuzz-${name}";
    runtimeInputs = [ pkgs.coreutils ];
    text = ''
      set -- runs "$@"
      ${prelude}
      echo "fuzz-${name}: writing to $run" >&2
      # Replaying a trace needs the spec it was recorded with.
      mkdir -p "$run/spec/lib" "$run/spec/harnesses/${name}"
      cp -r "$root/lib/spec" "$run/spec/lib/spec"
      cp "$root/harnesses/${name}/spec.ts" "$run/spec/harnesses/${name}/spec.ts"
      ${scripts.pinShell}
      status=0
      "''${pinned[@]}" ${bombadil.default}/bin/bombadil terminal fuzz \
        --specification "${specIn name "$run/spec"}" \
        --output-path "$run" \
        "$@" \
        -- ${launch} "$run" 2>&1 | tee "$run/bombadil.log" || status=$?
      ${finish "fuzz"}
    '';
  };

  replay = pkgs.writeShellApplication {
    name = "reproduce-${name}";
    runtimeInputs = [ pkgs.coreutils ];
    text = ''
      if [ $# -ne 1 ]; then
        echo "usage: reproduce-${name} <trace.jsonl or trace.jsonl.zst>" >&2
        exit 1
      fi
      ${scripts.resolveTrace}
      set -- reproductions
      ${prelude}
      spec="${specIn name "$snapshot"}"
      if [ -z "$snapshot" ]; then
        echo "reproduce-${name}: no spec snapshot, using the current spec" >&2
        spec="${specIn name "$root"}"
      fi
      set -- "$trace" "$run/input.jsonl"
      ${scripts.unpackTrace}
      ${scripts.pinShell}
      status=0
      "''${pinned[@]}" ${bombadil.default}/bin/bombadil terminal test \
        --specification "$spec" \
        --reproduce "$run/input.jsonl" \
        --output-path "$run/run" \
        -- ${launch} "$run" 2>&1 | tee "$run/bombadil.log" || status=$?
      ${finish "reproduce"}
    '';
  };
in
{
  apps = {
    "fuzz-${name}" = scripts.app fuzz;
    "reproduce-${name}" = scripts.app replay;
  };
}
