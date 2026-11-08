{ pkgs, bombadil }:
{ lib, ... }:
let
  dataDir = "/var/lib/syncthing-zoo";
  seed = pkgs.writeShellScript "syncthing-zoo-seed" ''
    set -eu
    install -d -m 700 -o syncthing -g syncthing \
      ${dataDir}/config ${dataDir}/database ${dataDir}/Sync/documents
    if [ ! -f ${dataDir}/Sync/readme.txt ]; then
      printf '%s\n' \
        'Bombadil Syncthing fixture' \
        "" \
        'These harmless files give the local dashboard something to scan.' \
        > ${dataDir}/Sync/readme.txt
    fi
    if [ ! -f ${dataDir}/Sync/documents/inventory.csv ]; then
      printf '%s\n' \
        'item,count' \
        'alpha,1' \
        'beta,2' \
        'gamma,3' \
        > ${dataDir}/Sync/documents/inventory.csv
    fi
    if [ ! -f ${dataDir}/Sync/documents/unicode.txt ]; then
      printf '%s\n' 'Norwegian: blåbær; Japanese: 同期; emoji: 🧪' \
        > ${dataDir}/Sync/documents/unicode.txt
    fi
    chown -R syncthing:syncthing ${dataDir}/Sync
  '';
in
{
  networking.hostName = "syncthing-zoo";
  services.syncthing = {
    enable = true;
    inherit dataDir;
    configDir = "${dataDir}/config";
    databaseDir = "${dataDir}/database";
    guiAddress = "127.0.0.1:8384";
    openDefaultPorts = false;
    overrideDevices = true;
    overrideFolders = true;
    settings = {
      options = {
        listenAddresses = [ ];
        globalAnnounceEnabled = false;
        localAnnounceEnabled = false;
        relaysEnabled = false;
        natEnabled = false;
        startBrowser = false;
        urAccepted = -1;
        autoUpgradeIntervalH = 0;
        crashReportingEnabled = false;
        stunServers = [ ];
      };
      folders.zoo-sample = {
        label = "Zoo Samples";
        path = "${dataDir}/Sync";
        type = "sendreceive";
        devices = [ ];
        rescanIntervalS = 60;
        fsWatcherEnabled = true;
      };
    };
  };
  systemd.services.syncthing.serviceConfig = {
    ExecStartPre = [ "+${seed}" ];
    # The Actions menu exposes both Restart and Shut Down. Keep later native
    # browser runs useful after either one stops the process.
    Restart = lib.mkForce "always";
    RestartSec = 1;
  };
}
