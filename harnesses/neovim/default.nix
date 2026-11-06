# Fuzz harness for Neovim.
#
# Neovim runs shell commands (`:!`, `:terminal`) and writes files, so
# campaigns run in the Nix sandbox. Every run starts `nvim --clean` on a
# fresh copy of a seed directory, with no user config or plugins.
{
  pkgs,
  zoo,
  ...
}:
let
  launch = zoo.launchInCopy {
    name = "neovim";
    seed = zoo.seeds.sourceFiles;
    # -n: no swap files, so runs don't trip over each other's recovery.
    command = "${pkgs.neovim}/bin/nvim --clean -n src/main.c src/app.py README.md big.txt";
    env = {
      HOME = ''"$work"'';
      XDG_STATE_HOME = ''"$work/.local/state"'';
      XDG_DATA_HOME = ''"$work/.local/share"'';
      SHELL = "${pkgs.bash}/bin/bash";
    };
  };
in
zoo.sandboxed {
  name = "neovim";
  inherit launch;
  inputs = [ pkgs.coreutils ];
  devShell.packages = [ pkgs.neovim ];
}
