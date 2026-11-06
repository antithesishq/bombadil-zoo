# Fuzz harness for tig, the text-mode interface for git.
#
# tig runs git and shell commands (`!`), so campaigns run in the Nix
# sandbox. Every run starts tig in a fresh copy of the shared git
# repository.
{
  pkgs,
  zoo,
  ...
}:
let
  launch = zoo.launchInCopy {
    name = "tig";
    seed = zoo.seeds.gitRepo;
    command = "${pkgs.tig}/bin/tig -C repo --all";
    env = {
      HOME = ''"$work"'';
      XDG_CONFIG_HOME = ''"$work/.config"'';
      GIT_CONFIG_GLOBAL = "${zoo.seeds.gitconfig}";
      EDITOR = "true";
      GIT_EDITOR = "true";
      PAGER = "cat";
    };
  };
in
zoo.sandboxed {
  name = "tig";
  inherit launch;
  inputs = [ pkgs.git ];
  devShell.packages = [ pkgs.tig ];
}
