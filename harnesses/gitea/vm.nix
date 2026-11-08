{ pkgs, bombadil }:
{ lib, ... }:
{
  services.gitea = {
    enable = true;
    package = pkgs.gitea;
    appName = "Bombadil Gitea Zoo";
    database.type = "sqlite3";
    settings = {
      server = {
        HTTP_ADDR = "127.0.0.1";
        HTTP_PORT = 3000;
        ROOT_URL = "http://127.0.0.1:3000/";
        DISABLE_SSH = true;
      };
      service = {
        DISABLE_REGISTRATION = true;
        REQUIRE_SIGNIN_VIEW = true;
      };
      security.INSTALL_LOCK = lib.mkForce true;
      session.COOKIE_SECURE = false;
      mailer.ENABLED = false;
      actions.ENABLED = false;
      "cron.update_checker".ENABLED = false;
    };
  };
}
