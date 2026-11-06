# Fuzz harness for Helix, the modal editor.
#
# Helix runs shell commands (`:sh`, `|`, `!`) and writes files, so
# campaigns run in the Nix sandbox. Every run starts hx on a fresh copy of
# the shared source files, with no user config.
{
  pkgs,
  zoo,
  ...
}:
let
  launch = zoo.launchInCopy {
    name = "helix";
    seed = zoo.seeds.sourceFiles;
    command = "${pkgs.helix}/bin/hx src/main.c src/app.py README.md big.txt";
    env = {
      HOME = ''"$work"'';
      XDG_CONFIG_HOME = ''"$work/.config"'';
      XDG_CACHE_HOME = ''"$work/.cache"'';
      SHELL = "${pkgs.bash}/bin/bash";
    };
  };
in
zoo.sandboxed {
  name = "helix";
  inherit launch;
  inputs = [ pkgs.coreutils ];
  devShell.packages = [ pkgs.helix ];
}
