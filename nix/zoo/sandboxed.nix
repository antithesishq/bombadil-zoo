# A harness whose campaigns run as Nix builds: no network, no access to your
# home directory. Use it for targets that can run commands or change files.
#
#   name        the harness directory under harnesses/
#   launch      script: launch <run dir>
#   inputs      extra tools on PATH during the campaign
#   crashLines  regex for crash lines on stderr
#   smokeArgs   bombadil arguments for the smoke check
{
  pkgs,
  bombadil,
  scripts,
}:
{
  name,
  launch,
  inputs ? [ ],
  crashLines ? scripts.defaultCrashLines,
  smokeArgs ? [
    "--time-limit-fuzz"
    "20s"
    "--time-limit-run"
    "5s"
  ],
}:
let
  inherit (pkgs) lib;
  inherit (scripts) finalize report specIn;

  env = ''
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME" "$out/stderr"
  '';

  finish = ''
    echo "$status" > "$out/status"
    ${finalize}/bin/zoo-finalize "$out" ${lib.escapeShellArg crashLines}
  '';

  # One campaign. seed makes every invocation a distinct derivation. The
  # build succeeds whatever the campaign finds, so the results survive;
  # bombadil's own exit status is kept in `status`.
  run =
    {
      seed ? "0",
      args ? [ ],
      cpus ? "",
    }:
    let
      specTree = scripts.specTreeOf name;
    in
    pkgs.runCommand "${name}-campaign-${seed}" { nativeBuildInputs = inputs; } ''
      ${env}
      cp -r ${specTree} "$out/spec"
      status=0
      ${scripts.pin cpus}${bombadil.default}/bin/bombadil terminal fuzz \
        --specification ${specIn name specTree} \
        --output-path "$out/trace.bin" \
        ${lib.escapeShellArgs args} \
        -- ${launch} "$out" > "$out/bombadil.log" 2>&1 || status=$?
      ${finish}
    '';

  # Replay and shrinking both execute recorded input, so keep both in the
  # sandbox. Each trial launches a fresh target through the harness's launch
  # script. specTree is the spec the trace was recorded with.
  replayRun =
    command:
    {
      trace,
      seed ? "0",
      cpus ? "",
      specTree ? scripts.specTreeOf name,
      args ? [ ],
    }:
    pkgs.runCommand "${name}-${command}-${seed}" { nativeBuildInputs = inputs; } ''
      ${env}
      cp -r ${specTree} "$out/spec"
      set -- ${trace} "$TMPDIR/trace.bin"
      ${scripts.unpackTrace}
      status=0
      ${scripts.pin cpus}${bombadil.default}/bin/bombadil terminal ${command} \
        --specification ${specIn name specTree} \
        --${if command == "shrink" then "trace" else "reproduce"} "$TMPDIR/trace.bin" \
        --output-path "$out/trace.bin" \
        ${lib.escapeShellArgs args} \
        -- ${launch} "$out" > "$out/bombadil.log" 2>&1 || status=$?
      ${if command == "shrink" then ''echo "$status" > "$out/status"'' else finish}
    '';

  reproduce = replayRun "test";
  shrink = replayRun "shrink";

  # An app that builds a campaign or replay from the working tree's flake and
  # copies the result into .state. Plain nix from PATH on purpose: the
  # client should match the system's Nix daemon.
  app =
    kind: build:
    pkgs.writeShellApplication {
      name = "${kind}-${name}";
      runtimeInputs = [
        pkgs.coreutils
        pkgs.jq
      ];
      text = ''
        ${scripts.findRoot}
        ts="$(date +%Y%m%d-%H%M%S)"
        dest="$root/.state/${name}/${
          if kind == "fuzz" then
            "runs"
          else if kind == "shrink" then
            "shrinks"
          else
            "reproductions"
        }/$ts"
        campaigns="(builtins.getFlake \"git+file://$root\").legacyPackages.${pkgs.stdenv.hostPlatform.system}.campaigns.${name}"

        echo "${kind}-${name}: building in the Nix sandbox" >&2
        ${build}

        mkdir -p "$dest"
        cp -r "$out"/. "$dest"
        chmod -R u+w "$dest"
        ${
          if kind == "shrink" then
            ''
              cat "$dest/bombadil.log"
              echo "shrink-${name}: results in $dest" >&2
              exit "$(cat "$dest/status")"
            ''
          else
            ''${report}/bin/zoo-report "$dest" "${kind}-${name}"''
        }
      '';
    };

  fuzz = app "fuzz" ''
    args="$(jq -nc '$ARGS.positional' --args -- "$@")"
    out="$(nix build --impure --no-link --print-out-paths -L \
      --argstr seed "$ts" --argstr args "$args" --argstr cpus "''${ZOO_CPUS:-}" \
      --expr "{ seed, args, cpus }: $campaigns.run { inherit seed cpus; args = builtins.fromJSON args; }")"
  '';

  traceApp =
    kind:
    let
      usage =
        "usage: ${kind}-${name} <trace.bin or trace.bin.zst>"
        + lib.optionalString (kind == "shrink") " [shrink options]";
    in
    app kind ''
      if [ "''${1:-}" = --help ]; then
        echo ${lib.escapeShellArg usage}
        ${bombadil.default}/bin/bombadil terminal ${if kind == "shrink" then "shrink" else "test"} --help
        exit 0
      fi
      if [ $# ${if kind == "reproduce" then "-ne" else "-lt"} 1 ]; then
        echo ${lib.escapeShellArg usage} >&2
        exit 1
      fi
      ${scripts.resolveTrace}
      args="$(jq -nc '$ARGS.positional' --args -- "$@")"
      if [ -n "$snapshot" ]; then
        echo "${kind}-${name}: using the campaign's spec in $snapshot" >&2
      else
        echo "${kind}-${name}: no spec snapshot, using the current spec" >&2
      fi
      out="$(nix build --impure --no-link --print-out-paths -L \
        --argstr seed "$ts" --argstr trace "$trace" --argstr snapshot "$snapshot" \
        --argstr cpus "''${ZOO_CPUS:-}" --argstr args "$args" \
        --expr "{ seed, trace, snapshot, cpus, args }: $campaigns.${kind} ({
          inherit seed cpus;
          args = builtins.fromJSON args;
          trace = builtins.path { path = trace; name = baseNameOf trace; };
        } // (if snapshot == \"\" then { } else {
          specTree = builtins.path { path = snapshot; name = \"spec\"; };
        }))")"
    '';

  # Proves the spec loads and the target starts in the sandbox. Fails only if
  # bombadil itself errors; violations are fine here.
  smoke = pkgs.runCommand "${name}-smoke" { } ''
    campaign=${
      run {
        seed = "smoke";
        args = smokeArgs;
      }
    }
    status="$(cat "$campaign/status")"
    if [ "$status" != 0 ] && [ "$status" != 2 ]; then
      echo "bombadil exited with $status:" >&2
      tail -20 "$campaign/bombadil.log" >&2
      exit 1
    fi
    touch "$out"
  '';
in
{
  apps = {
    "fuzz-${name}" = scripts.app fuzz;
    "reproduce-${name}" = scripts.app (traceApp "reproduce");
    "shrink-${name}" = scripts.app (traceApp "shrink");
  };
  legacyPackages.campaigns.${name} = { inherit run reproduce shrink; };
  checks."smoke-${name}" = smoke;
}
