{
  description = "Property-based fuzzing of terminal and browser UIs with Bombadil";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    # Deliberately not following our nixpkgs, so builds hit bombadil.cachix.org.
    bombadil.url = "github:antithesishq/bombadil";
    bombadil-external.url = "github:antithesishq/bombadil/6ee18c40bb9183d3ef707037cd89f7f771d761e8";
    bombadil-drivers.url = "github:antithesishq/bombadil-drivers/354f7df06d557a4ca9dd72cbf89facbce2366db4";
    rex-rune.url = "github:shuv1337/rex-rune";
  };

  nixConfig = {
    extra-substituters = [ "https://bombadil.cachix.org" ];
    extra-trusted-public-keys = [
      "bombadil.cachix.org-1:6L4epM9zwhEcAwouNgBa8ENtsgLNfedtQgqtdnQhZiM="
    ];
  };

  outputs =
    inputs@{ nixpkgs, bombadil, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      perSystem = f: nixpkgs.lib.genAttrs systems (system: f (zooFor system));

      zooFor =
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          bombadil' = bombadil.packages.${system};
          zoo = import ./nix/zoo {
            inherit pkgs;
            bombadil = bombadil';
          };
        in
        {
          inherit pkgs;
          bombadil = bombadil';
          harnesses = import ./nix/harnesses.nix {
            inherit pkgs zoo inputs;
            bombadil = bombadil';
          };
        };
    in
    {
      packages = perSystem (
        { bombadil, harnesses, ... }:
        {
          default = bombadil.default;
          bombadil = bombadil.default;
          bombadil-npm = bombadil.npm-package;
        }
        // harnesses.packages
      );

      apps = perSystem (
        { bombadil, harnesses, ... }:
        {
          default = {
            type = "app";
            program = "${bombadil.default}/bin/bombadil";
          };
        }
        // harnesses.apps
      );

      # The functions that build a campaign derivation per invocation.
      legacyPackages = perSystem ({ harnesses, ... }: harnesses.legacyPackages);

      # nix flake check: type-checks the specs, builds every package and runs
      # a short smoke campaign per sandboxed harness.
      checks = perSystem (
        {
          pkgs,
          bombadil,
          harnesses,
        }:
        import ./nix/checks.nix {
          inherit pkgs bombadil;
          externalNpmPackage =
            inputs.bombadil-external.packages.${pkgs.stdenv.hostPlatform.system}.npm-package;
        }
        // harnesses.packages
        // harnesses.checks
      );

      devShells = perSystem (
        {
          pkgs,
          bombadil,
          harnesses,
        }:
        import ./nix/devshell.nix {
          inherit pkgs bombadil;
          inherit (harnesses) harnesses;
        }
      );

      formatter = perSystem ({ pkgs, ... }: pkgs.nixfmt);
    };
}
