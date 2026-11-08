{
  pkgs,
  bombadil,
  zoo,
}:
zoo.browserVm {
  name = "syncthing";
  target = pkgs.syncthing;
  origin = "http://127.0.0.1:8384/";
  healthCheck = "curl -fsS http://127.0.0.1:8384/rest/noauth/health";
  serviceUnits = [
    "syncthing.service"
    "syncthing-init.service"
  ];
  coverage = ''
    any(.[]; any(.metadata.snapshots[];
      .name == "page" and .value.ready == true))'';
}
