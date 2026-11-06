# Fuzz harness for btop, the system monitor.
#
# btop can signal processes, so campaigns run in the Nix sandbox, and btop
# gets a PID namespace of its own inside it. There it is PID 1 and only
# sees itself, so its signal keys can't reach bombadil, and signals it sends
# itself as PID 1 are ignored.
{
  pkgs,
  zoo,
  ...
}:
let
  launch = zoo.launchInCopy {
    name = "btop";
    seed = pkgs.emptyDirectory;
    command = "${pkgs.util-linux}/bin/unshare --user --pid --fork --mount-proc ${pkgs.btop}/bin/btop";
    prepare = "mkdir -p .config";
    env = {
      HOME = ''"$work"'';
      XDG_CONFIG_HOME = ''"$work/.config"'';
    };
  };
in
zoo.sandboxed {
  name = "btop";
  inherit launch;
  devShell.packages = [ pkgs.btop ];
}
