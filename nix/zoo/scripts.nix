# Pieces shared by both runners: where specs come from, how a finished
# campaign is summarized and pruned, and how a target gets launched.
{ pkgs }:
let
  inherit (pkgs) lib;
  coreutils = "${pkgs.coreutils}/bin";
in
rec {
  # Matches the lines that identify a crash in stderr: Rust panics, Go panics
  # and runtime fatal errors, and Zig panics ("thread 18 panic: ...").
  defaultCrashLines = "panicked at |^panic: |^fatal error: |^thread [0-9]+ panic: ";

  # The spec of harness `name` together with the shared helpers it imports
  # from lib/spec, laid out as in the repository. Campaigns copy this tree
  # into their results as spec/, because replaying a trace needs the spec it
  # was recorded with.
  specTreeOf =
    name:
    lib.fileset.toSource {
      root = ../..;
      fileset = lib.fileset.unions [
        ../../lib/spec
        (../../harnesses + "/${name}/spec.ts")
      ];
    };

  specIn = name: tree: "${tree}/harnesses/${name}/spec.ts";

  # finalize <run dir> <crash regex>: summarizes a finished campaign into
  # `violations` and `crashes`, and keeps zstd-compressed traces only for
  # failures. External launchers prefix stderr files with BOMBADIL_RUN_ID so a
  # crash without a property violation still retains the matching trace. A full
  # campaign's traces run to hundreds of gigabytes.
  finalize = pkgs.writeShellApplication {
    name = "zoo-finalize";
    runtimeInputs = with pkgs; [
      coreutils
      findutils
      gawk
      gnugrep
      gnused
      zstd
    ];
    text = ''
      out="$1"
      crash_lines="$2"

      find "$out/stderr" -type f -empty -delete 2>/dev/null || true

      # bombadil reprints its summary on every refresh, and lines look like
      # "noPanic: 3, 17". The worker table has numbers too, so match the
      # shape exactly and keep the last line per property.
      sed 's/\x1b\[[0-9;]*[A-Za-z]//g' "$out/bombadil.log" \
        | grep -E '^[A-Za-z]+: [0-9]+(, [0-9]+)*$' \
        | awk -F: '{ last[$1] = $0 } END { for (p in last) print last[p] }' \
        | sort > "$out/violations" || true
      # A replay (terminal test) reports "noPanic was violated" instead.
      grep -oE '^[A-Za-z]+ was violated' "$out/bombadil.log" \
        | sort -u >> "$out/violations" || true

      # The distinct crash messages, most frequent first.
      cat "$out"/stderr/* 2>/dev/null \
        | grep -E "$crash_lines" \
        | sed -E -e 's/^thread .* panicked at /panicked at /' -e 's/^thread [0-9]+ panic: /panic: /' \
        | sort | uniq -c | sort -rn > "$out/crashes" || true

      violation_keep="$(cut -d: -f2 "$out/violations" | tr ',' '\n' | tr -d ' ')"
      crash_keep="$(
        for log in "$out"/stderr/*; do
          [ -f "$log" ] || continue
          if grep -Eq "$crash_lines" "$log"; then
            printf '%s\n' "''${log##*/}"
          fi
        done | sed -n 's/^\([0-9][0-9]*\)-.*$/\1/p'
      )"
      keep="$(printf '%s\n%s\n' "$violation_keep" "$crash_keep" | sed '/^$/d' | sort -un)"
      for trace in "$out"/trace-*.bin; do
        [ -f "$trace" ] || continue
        id="''${trace##*/trace-}"
        id="''${id%.bin}"
        if grep -qx "$id" <<< "$keep"; then
          zstd -q --rm "$trace"
        else
          rm "$trace"
        fi
      done
    '';
  };

  # report <run dir> <app name>: prints what a campaign or replay found.
  report = pkgs.writeShellApplication {
    name = "zoo-report";
    runtimeInputs = with pkgs; [
      coreutils
      gnugrep
      gnused
    ];
    text = ''
      out="$1"
      name="$2"
      # bombadil exits 0 when done and 2 on violations, but a replay (terminal
      # test) exits 1 for violations too, which it reports as such. Anything
      # else is a failure, e.g. a spec error or a trace the spec can't produce.
      status="$(cat "$out/status")"
      if [ "$status" != 0 ] && [ "$status" != 2 ] \
        && ! grep -q 'violation(s) reported' "$out/bombadil.log"; then
        echo "$name: bombadil failed with status $status:" >&2
        sed 's/\x1b\[[0-9;]*[A-Za-z]//g' "$out/bombadil.log" | grep -v '^\s*$' | tail -3 >&2
      fi
      if [ -s "$out/violations" ]; then
        echo "$name: violated properties (and their run IDs):" >&2
        cat "$out/violations" >&2
      else
        echo "$name: no violations" >&2
      fi
      if [ -s "$out/crashes" ]; then
        echo "$name: crashes on stderr:" >&2
        cat "$out/crashes" >&2
      fi
      echo "$name: results in $out" >&2
    '';
  };

  # Shell: writes the trace $1, given as trace.bin or trace.bin.zst, to $2.
  unpackTrace = ''
    case "$1" in
      *.zst) ${pkgs.zstd}/bin/zstd -dcq "$1" > "$2" ;;
      *) ${coreutils}/cp "$1" "$2" ;;
    esac
  '';

  # Shell: sets $root to the repository, so apps work from any subdirectory.
  findRoot = ''
    root="$(${pkgs.git}/bin/git rev-parse --show-toplevel 2>/dev/null || pwd)"
  '';

  # Shell: consumes the trace argument in $1, resolves it to $trace, and
  # finds the spec kept at <campaign>/spec beside trace-<id>.bin(.zst).
  # Sets $snapshot to "" when no saved spec exists; leaves any options in $@.
  resolveTrace = ''
    trace="$(${coreutils}/realpath "$1")"
    shift
    snapshot="$(${coreutils}/dirname "$trace")/spec"
    [ -d "$snapshot" ] || snapshot=""
  '';

  # --parallelism controls Bombadil's workers (default 1). CPU affinity
  # separately limits which cores they and their target processes use.
  # `pin cpus` prefixes a command with taskset for a list like "0-3", or with
  # nothing for "". The apps take the list from $ZOO_CPUS.
  pin = cpus: lib.optionalString (cpus != "") "${pkgs.util-linux}/bin/taskset --cpu-list ${cpus} ";

  # Shell: the same for the host runner, where $ZOO_CPUS is read at run time.
  # Use as "''${pinned[@]}" before the command.
  pinShell = ''
    pinned=()
    if [ -n "''${ZOO_CPUS:-}" ]; then
      pinned=(${pkgs.util-linux}/bin/taskset --cpu-list "$ZOO_CPUS")
      echo "pinned to CPUs $ZOO_CPUS" >&2
    fi
  '';

  app = drv: {
    type = "app";
    program = "${drv}/bin/${drv.name}";
  };

  # The shell part of a launch script: copies stderr to a file per process
  # under the run directory $1, and to the terminal so the spec sees crash
  # messages.
  teeStderr = ''2> >(${coreutils}/tee "$1/stderr/''${BOMBADIL_RUN_ID:-unknown}-$$" >&2)'';

  # Runs its arguments after the first with the directory in $1 hidden
  # behind an empty tmpfs, in user and mount namespaces of their own, as the
  # original user. The run directory is the campaign's own output, which the
  # build user can write. Without this, file managers walked up to it and
  # deleted bombadil's log and traces mid-campaign, which made campaigns look
  # clean.
  hideRunDir = pkgs.writeShellScript "zoo-hide-run-dir" ''
    export ZOO_UID="$(${coreutils}/id -u)" ZOO_GID="$(${coreutils}/id -g)"
    exec ${pkgs.util-linux}/bin/unshare --user --map-root-user --mount \
      ${pkgs.bash}/bin/bash -c '
        ${pkgs.util-linux}/bin/mount -t tmpfs -o size=1m,mode=000 zoo-hidden "$1" || exit 70
        shift
        exec ${pkgs.util-linux}/bin/unshare --user \
          --map-user="$ZOO_UID" --map-group="$ZOO_GID" -- "$@"
      ' bash "$@"
  '';

  # A launch script that starts `command` in a fresh, writable copy of
  # `seed`, so nothing one run changes leaks into the next.
  #
  #   prepare  shell run in the copy first, e.g. for entries a store path
  #            can't hold, like FIFOs or unreadable directories
  #   env      variables to export; values are shell words, so "$work"
  #            refers to the copy. LANG defaults to C.UTF-8: the sandbox
  #            sets no locale, and without one targets fall back to ASCII,
  #            or refuse to start, like btop.
  launchInCopy =
    {
      name,
      seed,
      command,
      prepare ? "",
      env ? { },
    }:
    pkgs.writeShellScript "${name}-launch" ''
      work="$(${coreutils}/mktemp -d)"
      ${coreutils}/cp -r ${seed}/. "$work"
      ${coreutils}/chmod -R u+w "$work"
      cd "$work"
      ${prepare}
      ${lib.concatStrings (
        lib.mapAttrsToList (k: v: "export ${k}=${v}\n") ({ LANG = "C.UTF-8"; } // env)
      )}
      exec ${hideRunDir} "$1" ${command} ${teeStderr}
    '';
}
