# Fuzz harness for atuin's interactive history search (`atuin search -i`).
#
# The seed is a history database imported from a generated zsh history.
# atuin can run commands from the history it shows, so campaigns run in the
# Nix sandbox. Every run starts on a fresh copy of the database.
{
  pkgs,
  zoo,
  ...
}:
let
  atuin = "${pkgs.atuin}/bin/atuin";

  # No sync, no update check and no daemon: everything stays local.
  #
  # inline_height = 0 keeps atuin fullscreen. By default, terminals taller
  # than 40 rows get an inline viewport, which asks the terminal for the
  # cursor position at startup and gives up with an error after 2s. Under
  # the fuzzer's typing that sometimes timed out, and the replay passed.
  config = pkgs.writeText "atuin-config.toml" ''
    auto_sync = false
    update_check = false
    sync_address = "http://127.0.0.1:9"
    enter_accept = false
    inline_height = 0
    [daemon]
    enabled = false
  '';

  # Commands of every shape the search UI has to render and filter: short
  # and long, multi-line, non-ASCII, wide characters, duplicates, failures.
  seed = pkgs.runCommand "atuin-seed" { } ''
    export HOME=$TMPDIR/home XDG_DATA_HOME=$out/data XDG_CONFIG_HOME=$out/config
    mkdir -p $HOME $XDG_CONFIG_HOME/atuin $XDG_DATA_HOME
    cp ${config} $XDG_CONFIG_HOME/atuin/config.toml

    history=$TMPDIR/zsh_history
    t=1700000000
    add() { t=$((t + 37)); printf ': %s:%s;%s\n' "$t" "$1" "$2" >> $history; }
    for i in $(seq 1 3000); do
      case $((i % 12)) in
        0) add 0 "git commit -m \"change $i\"" ;;
        1) add 2 "cargo build --release --features feature-$i" ;;
        2) add 0 "cd ~/projects/ünïcödé-$i" ;;
        3) add 1 "echo 日本語のコマンド $i" ;;
        4) add 0 "kubectl get pods -n fuzz -o wide | grep web-$i" ;;
        5) add 0 "ls" ;;
        6) add 0 "$(printf 'x%.0s' $(seq 1 300)) $i" ;;
        7) add 127 "nonexistent-command-$i --flag" ;;
        8) add 0 "for f in *.txt; do\\
      echo \"\$f\" $i\\
    done" ;;
        9) add 0 "ssh host-$i.example.com 'uptime; df -h'" ;;
        10) add 0 "nix run .#fuzz-yazi -- --time-limit-fuzz 10m" ;;
        11) add 0 "   leading and trailing spaces $i   " ;;
      esac
    done
    HISTFILE=$history ${atuin} import zsh
  '';

  # atuin exits after every selection or Esc. Restart it while it exits
  # cleanly, so a run keeps fuzzing; any other exit ends the run, so the
  # spec still sees crashes.
  #
  # Each restart takes the next of four setups, so a run also reaches the
  # vim keymaps and the inverted and compact layouts, which a single config
  # never shows. --keymap-mode only applies because the config leaves
  # keymap_mode at auto.
  search = pkgs.writeShellScript "atuin-search-loop" ''
    # Keys that arrive between two instances reach the terminal driver, not
    # atuin. With echo on, a multi-byte character split across reads showed
    # up as U+FFFD, which noReplacementChars flagged; with signals and line
    # editing on, Ctrl+C would end the loop and Ctrl+S stop all output.
    ${pkgs.coreutils}/bin/stty -echo -icanon -isig -ixon -iexten
    i=0
    while :; do
      case $((i % 4)) in
        0) ${atuin} search -i --keymap-mode emacs ;;
        1) ${atuin} search -i --keymap-mode vim-insert ;;
        2) ATUIN_INVERT=true ${atuin} search -i --keymap-mode vim-normal ;;
        3) ATUIN_STYLE=compact ${atuin} search -i --keymap-mode emacs ;;
      esac || exit
      i=$((i + 1))
    done
  '';

  launch = zoo.launchInCopy {
    name = "atuin";
    inherit seed;
    command = "${search}";
    env = {
      HOME = ''"$work"'';
      XDG_DATA_HOME = ''"$work/data"'';
      XDG_CONFIG_HOME = ''"$work/config"'';
      ATUIN_SESSION = "0192d2e0a4a07c3a9c1e5e5f5b5c5d5e";
    };
  };
in
zoo.sandboxed {
  name = "atuin";
  inherit launch;
  devShell.packages = [ pkgs.atuin ];
}
// {
  packages.atuin-seed = seed;
}
