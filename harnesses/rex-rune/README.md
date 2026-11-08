# Rex: Rune driver example

Fuzzes the native Linux [Rex client](https://github.com/shuv1337/rex-rune) through
the in-process [`bombadil-rune` driver](https://github.com/antithesishq/bombadil-drivers/tree/main/drivers/rune).
Requires **x86_64 Linux**, Nix sandboxing and a host-installed Rex Nix package.
No running server, display server, KVM or GPU is needed; screenshots use Mesa's
software Vulkan renderer.

## Running

Select the Rex package, not its host profile or running server:

```sh
export ZOO_REX_PACKAGE="$(dirname "$(dirname "$(readlink -f "$(command -v rex)")")")"
nix run .#fuzz-rex-rune -- --time-limit-fuzz 2m --time-limit-run 15s
nix run .#reproduce-rex-rune -- .state/rex-rune/runs/<timestamp>/trace-0.bin.zst
nix run .#shrink-rex-rune -- .state/rex-rune/runs/<timestamp>/trace-0.bin.zst --time-limit 2m
nix build --impure --builders '' .#checks.x86_64-linux.rex-rune-protocol
nix develop .#rex-rune
```

`ZOO_REX_PACKAGE` must point to an existing `/nix/store/<package>` containing
`bin/rex`. Campaigns and checks read it during impure evaluation; the lockfile
does not record its path or version. Campaign and replay commands disable remote
builders. Server-dependent builds run locally and cannot be substituted.
**Do not upload or cache their closures:** they reference the host-provided binary.

Each session gets a fresh home, workspace, private Unix socket and Rex server.
The launcher seeds a `Zoo sandbox` Bash session and stops the server when the
client exits. Host configuration, credentials, desktop sockets and live sessions
are not mounted. Terminal commands run inside the Nix build sandbox without
network access. Review artifacts before sharing them.

## Coverage and limits

Actions exercise sessions, tabs, split panes, terminal search, command palettes,
Settings, pickers, forms and dialogs. They include crowded layouts, pane destruction,
modal transitions, edge clicks, Unicode editing and terminal escape sequences.
Thirty properties inspect the public element tree for geometry, clipping, focus,
identity, ownership and lifecycle errors.

This is grey-box UI testing, not OS accessibility or compositor automation.
It does not verify terminal emulation, server protocol correctness, native window
management, clipboard or desktop services. The driver does not support modifier
chords, dragging or window resizing. Rex's logical-key fallback can drop punctuation
and Unicode, so terminal payloads do not prove unchanged delivery to the PTY.

Background connections use real time. Observations report `settled: false`, and
replay or shrinking can be timing-sensitive.

## Implementation

The lockfile pins the Rex Rune client to 0.7.0. The `rex-rune`, `bombadil-drivers`
and `bombadil-external` inputs are independent of Zoo's terminal/browser engine.
The application patch adds an optional `bombadil` Cargo feature, activated by
`REX_BOMBADIL`. It uses Rex's real application and vendored Rune runtime, not a
mock UI. A Rune patch drains background updates before headless drawing; an engine
patch aligns its wire tag with the driver's `apply_action` contract.

The protocol check connects the patched client to its private server, requires a
terminal grid, opens Settings and checks the resulting element tree. It saves
`default.png`, `settings.png` and the JSONL exchange.

## Results

Results use the standard layout under `.state/rex-rune/runs/`. Campaigns retain
only property-violation and crash traces, compressed as `.bin.zst`, with the spec
and stderr. Inspect `violations` and `bombadil.log`; the engine's exit status alone
does not show whether properties passed.

Use `nix run .#bombadil-external -- trace --json FILE` to inspect a decompressed
trace, or `nix run .#bombadil-external -- external ...` for direct engine commands.
The harness shell adds the patched Rex client and `jq` to Zoo's spec-editing tools;
it does not include the ordinary Bombadil engine.
