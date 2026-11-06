# Fuzz harness for yazi, the terminal file manager.
#
# yazi's shell prompts run whatever is typed into them, so campaigns run in
# the Nix sandbox. Every run starts yazi in a fresh copy of a seed tree.
{
  pkgs,
  zoo,
  ...
}:
let
  # yazi with our fixes that are pending upstream, so fuzzing doesn't keep
  # rediscovering the same crashes.
  yazi = pkgs.yazi.override {
    yazi-unwrapped = pkgs.yazi-unwrapped.overrideAttrs (old: {
      patches = (old.patches or [ ]) ++ [
        ./patches/0001-input-op-range.patch
        ./patches/0002-input-kill-cursor.patch
      ];
    });
  };

  launch = zoo.launchInCopy {
    name = "yazi";
    seed = zoo.seeds.fileTree;
    prepare = zoo.seeds.fileTreePrepare;
    command = "${yazi}/bin/yazi";
    env.EDITOR = "true";
  };
in
zoo.sandboxed {
  name = "yazi";
  inherit launch;
  inputs = with pkgs; [
    # MIME detection.
    file
    # Search (s, S) and the fzf jump (Z).
    fd
    ripgrep
    fzf
  ];
  devShell.packages = [ yazi ];
}
// {
  packages = {
    inherit yazi;
    yazi-upstream = pkgs.yazi;
  };
}
