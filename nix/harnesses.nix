# Imports every directory under harnesses/ and merges what they provide.
#
# A harness's default.nix takes { pkgs, bombadil, zoo } and returns packages,
# apps, a devShell and optionally checks and legacyPackages, mostly via
# zoo.sandboxed or zoo.host.
# Additional named arguments are resolved from the flake inputs.
{
  pkgs,
  bombadil,
  zoo,
  inputs,
}:
let
  inherit (pkgs) lib;

  names = builtins.attrNames (
    lib.filterAttrs (_: type: type == "directory") (builtins.readDir ../harnesses)
  );

  harnesses = lib.genAttrs names (
    name: lib.callPackageWith (inputs // { inherit pkgs bombadil zoo; }) (../harnesses + "/${name}") { }
  );

  merge = attr: lib.concatMapAttrs (_: h: h.${attr} or { }) harnesses;
in
{
  inherit harnesses;
  packages = merge "packages";
  apps = merge "apps";
  checks = merge "checks";
  # Nested, e.g. campaigns.<name>, so merge recursively.
  legacyPackages = lib.foldl' lib.recursiveUpdate { } (
    lib.mapAttrsToList (_: h: h.legacyPackages or { }) harnesses
  );
}
