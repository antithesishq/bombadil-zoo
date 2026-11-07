# Fuzz harness for k9s, the Kubernetes TUI.
#
# k9s needs a cluster, so it runs on the host against a throwaway kind
# cluster loaded with fixtures (cluster.yaml), with all kube and k9s state
# under .state/k9s and --readonly so it can't change the cluster.
{
  pkgs,
  zoo,
  ...
}:
let
  # The tview version k9s requires, with our fix applied.
  tview = pkgs.applyPatches {
    name = "tview-patched";
    src = pkgs.fetchFromGitHub {
      owner = "derailed";
      repo = "tview";
      rev = "v0.8.5";
      hash = "sha256-16a/WQSfDWk7TdVyayu2GTIJ4S+ORtKqCNtk5JXMwUQ=";
    };
    patches = [ ./patches/tview/0001-textview-wrap-display-width.patch ];
  };

  # k9s master, which upstream works on, with our fixes that aren't merged
  # yet, so fuzzing doesn't keep rediscovering the same crashes. Drop a
  # patch once its fix lands, and bump rev to pick it up.
  k9s = pkgs.k9s.overrideAttrs (old: {
    version = "0.51.0-unstable-2026-11-06";
    src = pkgs.fetchFromGitHub {
      owner = "derailed";
      repo = "k9s";
      rev = "423fff9c371d751b8d2928f56d37fba6fb8ebc50";
      hash = "sha256-WiED1ybmOJzf4MphDPP02AyUo6l2TOtxy6NRFxZN9Zo=";
    };
    vendorHash = "sha256-3MVuybkrw1ykd0tLf5BQeUEz0eiNJS/Glm2PjXh8kXc=";
    patches = [
      ./patches/k9s/0001-cmdbuff-listener-race.patch
      ./patches/k9s/0002-table-no-api-version.patch
      ./patches/k9s/0003-xray-invalid-filter-rx.patch
      ./patches/k9s/0004-suggest-alias-race.patch
      ./patches/k9s/0005-xray-filter-before-load.patch
      ./patches/k9s/0006-recorder-send-on-closed.patch
      ./patches/k9s/0007-table-scheme-race.patch
    ];
    # Build against the patched tview. A directory replace doesn't change
    # the module set, so vendorHash stays the same.
    postPatch = (old.postPatch or "") + ''
      cp -r ${tview} ../tview
      chmod -R u+w ../tview
      echo 'replace github.com/derailed/tview => ../tview' >> go.mod
    '';
  });

  kubectl = "${pkgs.kubectl}/bin/kubectl";
  kind = "${pkgs.kind}/bin/kind";

  # Points kube and k9s at state under $state, so k9s can never reach a
  # real cluster or your own config.
  isolate = ''
    export KUBECONFIG="$state/kubeconfig"
    export K9S_CONFIG_DIR="$state/config"
    export XDG_STATE_HOME="$state/xdg"
    mkdir -p "$K9S_CONFIG_DIR" "$XDG_STATE_HOME"
  '';

  launch = pkgs.writeShellScript "k9s-launch" ''
    # Views that edit or open files, e.g. screen dumps, would otherwise
    # launch the user's editor, which outlives the campaign.
    export EDITOR=true VISUAL=true KUBE_EDITOR=true K9S_EDITOR=true
    exec ${k9s}/bin/k9s --readonly --logFile "$1/k9s.log" ${zoo.teeStderr}
  '';
in
zoo.host {
  name = "k9s";
  inherit launch;
  setup = ''
    ${isolate}
    # The cluster is throwaway and shared by every checkout, e.g. worktrees
    # fuzzing in parallel. Without a working kubeconfig, first try the
    # existing cluster's. Only if its API server doesn't answer either (e.g.
    # the node container stopped on reboot), recreate it rather than fuzz k9s
    # against a dead connection.
    ready() { ${kubectl} --request-timeout=5s get --raw /readyz >/dev/null 2>&1; }
    if ! ready && ${kind} get clusters 2>/dev/null | grep -qx fuzz; then
      ${kind} export kubeconfig --name fuzz >/dev/null 2>&1 || true
    fi
    if ! ready; then
      ${kind} delete cluster --name fuzz >/dev/null 2>&1 || true
      ${kind} create cluster --name fuzz
    fi
    # Fixtures are idempotent, so applying them every time is cheap and
    # restores anything a previous campaign's cron jobs changed.
    ${kubectl} apply -f ${./cluster.yaml} >/dev/null
    ${kubectl} wait --for condition=established --timeout=60s crd/widgets.fuzz.example.com >/dev/null
    ${kubectl} apply -f ${./widgets.yaml} >/dev/null
  '';
  devShell = {
    packages = [
      k9s
      pkgs.kind
      pkgs.kubectl
    ];
    shellHook = ''
      state="$PWD/.state/k9s"
      ${isolate}
    '';
  };
}
// {
  packages = {
    inherit k9s;
    k9s-upstream = pkgs.k9s;
  };
}
