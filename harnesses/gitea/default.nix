{
  pkgs,
  bombadil,
  zoo,
}:
zoo.browserVm {
  name = "gitea";
  target = pkgs.gitea;
  origin = "http://127.0.0.1:3000/user/login";
  healthCheck = "curl -fsS http://127.0.0.1:3000/user/login > /dev/null";
  coverage = ''
    any(.[]; any(.metadata.snapshots[];
      .name == "page" and .value.signedIn == true))'';
  prepare = ./prepare.py;
  # The pinned Chromium/Bombadil combination stalls on post-login navigation
  # with PauseIfNetworkFetchesPending. Keep the working policy as the default.
  virtualTimePolicy = "Advance";
  extraPackages = [ pkgs.git ];
}
