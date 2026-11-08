# The harness library, passed to every harness as `zoo`.
#
# A harness describes how to launch one instance of its target and hands
# that to a runner:
#
#   zoo.sandboxed  the campaign runs as a Nix build (sandboxed.nix)
#   zoo.host       the campaign runs on your machine (host.nix)
#   zoo.browserVm  a browser campaign in a disposable offline VM (browser-vm.nix)
#
# Browser harnesses provide their target service and smoke/spec files instead of
# implementing VM launch, result collection and replay separately.
#
# `launch <run dir>` starts one target process. It writes the target's stderr
# to <run dir>/stderr/<run-id>-<pid> and to the terminal, which zoo.teeStderr
# does, so the spec sees crash messages and finalization can retain external
# crash traces. The run ID is `unknown` for interfaces that do not provide one.
# zoo.launchInCopy builds such a script for
# targets that work on a copy of some seed state. Either runner gives the
# harness fuzz-<name> and reproduce-<name> apps that write results to
# .state/<name>/. Both accept `devShell`, an attribute set passed to mkShell.
{ pkgs, bombadil }:
let
  scripts = import ./scripts.nix { inherit pkgs; };
  runner =
    path:
    {
      devShell ? { },
      ...
    }@args:
    import path { inherit pkgs bombadil scripts; } (builtins.removeAttrs args [ "devShell" ])
    // {
      devShell = pkgs.mkShell devShell;
    };
in
{
  sandboxed = runner ./sandboxed.nix;
  host = runner ./host.nix;
  browserVm = import ./browser-vm.nix { inherit pkgs bombadil scripts; };
  inherit (scripts)
    app
    teeStderr
    launchInCopy
    defaultCrashLines
    ;
  seeds = import ./seeds.nix { inherit pkgs; };
}
