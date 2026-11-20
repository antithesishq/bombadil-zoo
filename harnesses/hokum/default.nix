{ pkgs, ... }:
if pkgs.stdenv.hostPlatform.system != "x86_64-linux" then
  { devShell = pkgs.mkShell { }; }
else
  let
    runner = pkgs.writeShellApplication {
      name = "run-hokum";
      runtimeInputs = [
        pkgs.python3
        pkgs.nix
        pkgs.gitMinimal
      ];
      text = ''exec python3 ${./.}/run.py "$@"'';
    };
  in
  {
    apps.fuzz-hokum = {
      type = "app";
      program = "${runner}/bin/run-hokum";
    };
    devShell = pkgs.mkShell {
      packages = [
        pkgs.python3
        pkgs.nix
      ];
    };
  }
