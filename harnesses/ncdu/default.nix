# Fuzz harness for ncdu, the disk usage analyzer.
#
# ncdu can delete files and spawn a shell, so campaigns run in the Nix
# sandbox. Every run scans a fresh copy of the shared file tree.
{
  pkgs,
  zoo,
  ...
}:
let
  launch = zoo.launchInCopy {
    name = "ncdu";
    seed = zoo.seeds.fileTree;
    prepare = zoo.seeds.fileTreePrepare;
    # --extended stores mtimes, so the spec can sort and show them (m, M).
    command = "${pkgs.ncdu}/bin/ncdu --extended --color dark .";
    env = {
      HOME = ''"$work"'';
      XDG_CONFIG_HOME = ''"$work/.config"'';
      SHELL = "${pkgs.bash}/bin/bash";
    };
  };
in
zoo.sandboxed {
  name = "ncdu";
  inherit launch;
  devShell.packages = [ pkgs.ncdu ];
}
