{
  pkgs,
  bundle,
  dependencies ? [ ],
  backend ? "mock",
}:
assert builtins.elem backend [
  "mock"
  "pipewire"
];
pkgs.testers.runNixOSTest {
  name = "hokum-rpc";
  nodes.machine = { lib, ... }: {
    virtualisation = {
      memorySize = 4096;
      cores = 2;
      diskSize = 4096;
      restrictNetwork = true;
      # Register embedded ELF interpreter/RPATH dependencies and their closures.
      additionalPaths = [ bundle ] ++ dependencies;
      useHostCerts = false;
    };
    # The test driver uses the system bus to launch a sandboxed transient unit.
    # The campaign cannot access its sockets (see test.py).
    networking.useDHCP = false;
    users.users.fuzzer = {
      isNormalUser = true;
      uid = 1000;
      extraGroups = [ "systemd-journal" ];
    };
    environment.systemPackages =
      with pkgs;
      [
        (python3.withPackages (p: [ p.pillow ]))
        jq
        vulkan-loader
        mesa
        fontconfig
        libxkbcommon
        dejavu_fonts
      ]
      ++ lib.optionals (backend == "pipewire") [ pkgs.pipewire ];
    fonts.packages = [ pkgs.dejavu_fonts ];
    # A dedicated daemon, not the NixOS desktop/user audio service. No ALSA,
    # Bluetooth, PulseAudio, WirePlumber, or D-Bus discovery is involved.
    environment.etc."hokum-pipewire.conf".text = ''
      context.properties = {
        core.daemon = true
        core.name = pipewire-0
        default.clock.rate = 48000
        default.clock.quantum = 1024
      }
      context.spa-libs = { audio.convert.* = audioconvert/libspa-audioconvert
                           support.* = support/libspa-support }
      context.modules = [
        { name = libpipewire-module-protocol-native }
        { name = libpipewire-module-metadata }
        { name = libpipewire-module-spa-node-factory }
        { name = libpipewire-module-client-node }
        { name = libpipewire-module-adapter }
        { name = libpipewire-module-link-factory }
        { name = libpipewire-module-access }
      ]
      context.objects = [
        { factory = metadata args = { metadata.name = default } }
        { factory = adapter args = {
            factory.name = support.null-audio-sink
            node.name = bombadil-output
            node.description = "Hokum virtual output"
            media.class = Audio/Sink
            node.virtual = true
            audio.position = [ FL FR ]
        } }
        { factory = adapter args = {
            factory.name = support.null-audio-sink
            node.name = bombadil-input
            node.description = "Hokum virtual input"
            media.class = Audio/Source
            node.virtual = true
            audio.position = [ FL FR ]
        } }
      ]
    '';
    systemd.services.hokum-pipewire = lib.mkIf (backend == "pipewire") {
      description = "Isolated Hokum virtual audio graph";
      environment = {
        XDG_RUNTIME_DIR = "/tmp/hokum-runtime";
        PIPEWIRE_REMOTE = "pipewire-0";
      };
      preStart = "install -d -m 0700 /tmp/hokum-runtime";
      serviceConfig = {
        User = "fuzzer";
        ExecStart = "${pkgs.pipewire}/bin/pipewire -c /etc/hokum-pipewire.conf";
        PrivateNetwork = true;
        PrivateDevices = true;
        NoNewPrivileges = true;
        InaccessiblePaths = [
          "-/run/dbus"
          "-/run/user"
        ];
      };
    };
    environment.etc."hokum-env".text = ''
      export PATH=/run/current-system/sw/bin
      export VK_ICD_FILENAMES=${pkgs.mesa}/share/vulkan/icd.d/lvp_icd.x86_64.json
      export VK_DRIVER_FILES=${pkgs.mesa}/share/vulkan/icd.d/lvp_icd.x86_64.json
      export LD_LIBRARY_PATH=${
        pkgs.lib.makeLibraryPath [
          pkgs.vulkan-loader
          pkgs.fontconfig
          pkgs.libxkbcommon
          pkgs.wayland
        ]
      }
      export WGPU_BACKEND=vulkan
      export DBUS_SESSION_BUS_ADDRESS=unix:path=/nonexistent-bombadil-bus
      export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/nonexistent-bombadil-bus
      export HOKUM_BACKEND=${backend}
      export XDG_RUNTIME_DIR=/tmp/hokum-runtime
      export PIPEWIRE_REMOTE=pipewire-0
    '';
  };
  testScript = builtins.readFile ./test.py;
  globalTimeout = 86400;
}
