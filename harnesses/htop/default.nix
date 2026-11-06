# Fuzz harness for htop, the process viewer.
#
# htop can signal and renice processes, so campaigns run in the Nix
# sandbox, and htop gets a PID namespace of its own inside it.
{
  pkgs,
  zoo,
  ...
}:
let
  bash = "${pkgs.bash}/bin/bash";
  sleep = "${pkgs.coreutils}/bin/sleep";

  # Runs as PID 1 of the namespace: starts a few processes for htop to
  # list, sort, tag, renice and show as a tree, then becomes htop. Their
  # names are valid UTF-8 with wide, combining and emoji characters, so
  # the process table has to cut them at column boundaries, but nothing
  # in them is invalid or unprintable, which htop would show as U+FFFD
  # on purpose.
  #
  # Each is a bash that waits on a sleep, since bash doesn't care what
  # its argv[0] is and coreutils, a single binary, picks the program by
  # it. The "; :" keeps bash from replacing itself with the sleep. A
  # command name (comm) comes from the file name, which the kernel cuts
  # at 15 bytes, so the symlinks' names are 15 bytes or less and end on a
  # character boundary.
  start = pkgs.writeShellScript "htop-start" ''
    mkdir bin
    ln -s ${bash} "bin/进程监视器"
    ln -s ${bash} "bin/😀😀😀"
    wait_on='${sleep} 1d; :'
    (exec -a "进程监视器" "bin/进程监视器" -c "$wait_on") &
    (exec -a "😀 ünïcödé 日本語のとても長いコマンドライン 한국어 café" "bin/😀😀😀" -c "$wait_on") &
    # Combining accents (U+0301, U+0308), as bytes so the line stays ASCII.
    (exec -a $'cafe\xcc\x81 nai\xcc\x88ve' ${bash} -c "$wait_on") &
    (exec -a "sleeper${
      pkgs.lib.concatStrings (pkgs.lib.genList (i: " --option-${toString i}=value") 40)
    }" ${bash} -c "$wait_on") &
    ${bash} -c '${sleep} 1d & ${sleep} 2d & wait' &
    exec ${pkgs.htop}/bin/htop
  '';

  launch = zoo.launchInCopy {
    name = "htop";
    seed = pkgs.emptyDirectory;
    prepare = "mkdir -p .config";
    # A PID namespace of its own, where htop is PID 1 and only sees itself
    # and the processes above, so its kill keys can't reach bombadil.
    command = "${pkgs.util-linux}/bin/unshare --user --pid --fork --mount-proc ${start}";
    env = {
      HOME = ''"$work"'';
      XDG_CONFIG_HOME = ''"$work/.config"'';
    };
  };
in
zoo.sandboxed {
  name = "htop";
  inherit launch;
  # The strace (s) and lsof (l) views run these.
  inputs = [
    pkgs.strace
    pkgs.lsof
  ];
  devShell.packages = [ pkgs.htop ];
}
