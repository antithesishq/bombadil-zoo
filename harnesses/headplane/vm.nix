{ pkgs, bombadil }:
{ ... }:
{
  virtualisation = {
    memorySize = 4096;
    cores = 2;
    diskSize = 4096;
    # Neither browser actions nor the target can contact real services.
    restrictNetwork = true;
  };
  services.headscale = {
    enable = true;
    settings = {
      server_url = "http://127.0.0.1:8080";
      dns = {
        base_domain = "zoo.test";
        override_local_dns = false;
      };
      derp = {
        urls = [ ];
        server = {
          enabled = true;
          region_id = 999;
          stun_listen_addr = "127.0.0.1:3478";
        };
      };
      policy.mode = "database";
    };
  };
  services.headplane = {
    enable = true;
    settings = {
      server = {
        host = "127.0.0.1";
        port = 3000;
        base_url = "http://127.0.0.1:3000";
        cookie_secure = false;
        # Public fixture secret, exclusively for this isolated VM.
        cookie_secret_path = pkgs.writeText "headplane-test-cookie" "01234567890123456789012345678901";
      };
      integration.proc.enabled = false;
    };
  };
  environment.systemPackages = [
    bombadil.default
    pkgs.chromium
    pkgs.curl
    pkgs.jq
    (pkgs.python3.withPackages (p: [ p.playwright ]))
  ];
  environment.etc = {
    "headplane-zoo/spec.ts".source = ./spec.ts;
    "headplane-zoo/smoke.py".source = ./smoke.py;
    "headplane-zoo/builds.json".text = builtins.toJSON {
      headplane = toString pkgs.headplane;
      headscale = toString pkgs.headscale;
      chromium = toString pkgs.chromium;
      bombadil = toString bombadil.default;
    };
  };
}
