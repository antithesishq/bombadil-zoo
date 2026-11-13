# The default shell has spec-editing tools only. Harness tools are opt-in,
# e.g. `nix develop .#yazi`; fuzz campaigns use `nix run .#fuzz-yazi`.
{
  pkgs,
  bombadil,
  harnesses,
}:
let
  inherit (pkgs) lib;

  base = pkgs.mkShell {
    packages = with pkgs; [
      # Writing specs.
      bun
      typescript
      typescript-language-server
      biome

      nil
      nixfmt
    ];

    # Exports rather than attributes, because mkShell's inputsFrom carries
    # shellHooks over but not plain environment variables. The node_modules
    # link lets editors resolve the Bombadil types.
    shellHook = ''
      export BOMBADIL_NPM_PACKAGE="${bombadil.npm-package}"
      mkdir -p node_modules/@antithesishq
      ln -sfn "$BOMBADIL_NPM_PACKAGE" node_modules/@antithesishq/bombadil
    '';
  };

  shellWith = shells: pkgs.mkShell { inputsFrom = [ base ] ++ shells; };
in
{
  default = base;
}
// lib.mapAttrs (_: h: shellWith [ h.devShell ]) harnesses
