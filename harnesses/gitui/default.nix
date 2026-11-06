# Fuzz harness for gitui, the git TUI written in Rust.
#
# gitui stages, commits, discards and pushes, so campaigns run in the Nix
# sandbox. Every run starts it in a fresh copy of the shared git repository.
{
  pkgs,
  zoo,
  ...
}:
let
  launch = zoo.launchInCopy {
    name = "gitui";
    seed = zoo.seeds.gitRepo;
    command = "${pkgs.gitui}/bin/gitui --directory repo";
    env = {
      HOME = ''"$work"'';
      XDG_CONFIG_HOME = ''"$work/.config"'';
      XDG_CACHE_HOME = ''"$work/.cache"'';
      GIT_CONFIG_GLOBAL = "${zoo.seeds.gitconfig}";
      EDITOR = "true";
      GIT_EDITOR = "true";
    };
  };
in
zoo.sandboxed {
  name = "gitui";
  inherit launch;
  inputs = [ pkgs.git ];
  devShell.packages = [ pkgs.gitui ];
}
