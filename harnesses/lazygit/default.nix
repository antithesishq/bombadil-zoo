# Fuzz harness for lazygit, the git TUI.
#
# lazygit runs git commands, custom shell commands (`:`) and can discard
# work, so campaigns run in the Nix sandbox. Every run starts lazygit in a
# fresh copy of a seed repository with a local remote.
{
  pkgs,
  zoo,
  ...
}:
let
  # No update checks or startup popups, so runs start in the main view.
  config = pkgs.writeText "lazygit.yml" ''
    update:
      method: never
    disableStartupPopups: true
    gui:
      showRandomTip: false
    # lazygit only takes $EDITOR when it names an editor it has a preset
    # for, and otherwise runs vim, so set the commands themselves.
    os:
      edit: "true"
      editAtLine: "true"
      editAtLineAndWait: "true"
      openDirInEditor: "true"
  '';

  launch = zoo.launchInCopy {
    name = "lazygit";
    seed = zoo.seeds.gitRepo;
    command = "${pkgs.lazygit}/bin/lazygit --path repo";
    env = {
      GIT_CONFIG_GLOBAL = "${zoo.seeds.gitconfig}";
      LG_CONFIG_FILE = "${config}";
      XDG_CONFIG_HOME = ''"$work/.config"'';
      XDG_STATE_HOME = ''"$work/.state"'';
      # Every way lazygit and git look for an editor, so edits return at
      # once instead of falling back to vim, which isn't there.
      EDITOR = "true";
      VISUAL = "true";
      GIT_EDITOR = "true";
    };
  };
in
zoo.sandboxed {
  name = "lazygit";
  inherit launch;
  # lazygit runs git from PATH.
  inputs = [ pkgs.git ];
  # lazygit reports errors it doesn't expect through log.Fatalf, behind a
  # timestamp, then exits.
  crashLines = "An error occurred! Please create an issue|^panic: |^fatal error: ";
  devShell.packages = [ pkgs.lazygit ];
}
