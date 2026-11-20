{
  pkgs,
  bombadil,
  model,
}:
{ ... }:
let
  modelDir = pkgs.linkFarm "llama-webui-models" [
    {
      name = "zoo-tiny.gguf";
      path = model;
    }
  ];
in
{
  virtualisation = {
    memorySize = 4096;
    cores = 2;
    diskSize = 4096;
    restrictNetwork = true;
  };
  systemd.services.llama-webui = {
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      ExecStart = "${pkgs.llama-cpp}/bin/llama-server --host 127.0.0.1 --port 8080 --models-dir ${modelDir} --models-max 1 --ctx-size 2048 --parallel 2 --threads 2 --n-predict 64 --seed 42 --jinja --chat-template chatml --offline";
      DynamicUser = true;
      PrivateTmp = true;
      ProtectHome = true;
      ProtectSystem = "strict";
      RuntimeDirectory = "llama-webui";
      WorkingDirectory = "/run/llama-webui";
    };
    environment = {
      HOME = "/run/llama-webui";
      XDG_CACHE_HOME = "/run/llama-webui/cache";
      HF_HOME = "/run/llama-webui/huggingface";
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
    "llama-webui-zoo/spec.ts".source = ./spec.ts;
    "llama-webui-zoo/smoke.py".source = ./smoke.py;
    "llama-webui-zoo/builds.json".text = builtins.toJSON {
      llama = toString pkgs.llama-cpp;
      inherit model;
      chromium = toString pkgs.chromium;
      bombadil = toString bombadil.default;
    };
  };
}
