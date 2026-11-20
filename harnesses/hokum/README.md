# Hokum: external black-box RPC fuzzing

The target is an ordinary, unmodified Hokum binary. No Bombadil library,
Rune runtime hook, scene, internal element tree or backend snapshot is used.
The standalone `bombadil-rune` package implements the JSONL RPC protocol.
There is no second Hokum-specific driver implementation here.

Each session starts a private guest D-Bus and headless Sway desktop, launches
`hokum sound` normally, sends compositor pointer events and `wtype` keyboard
events, and captures the desktop with `grim`. State contains process liveness,
public compositor window metadata, and journal entries since the last cursor.
The specification chooses log sources, levels and failure rules. Collection
errors abort the session; they do not become an empty successful log batch.
Log arrival is asynchronous, and observations explicitly report `settled:false`.

## Run

Supply a bundle containing `hokum`, the RPC-capable `bombadil` binary,
`rune-driver` and `spec.ts`. Build `bombadil-rune` with `nix build` and copy
`result/bin/bombadil-rune` into the bundle as `rune-driver` (dereference it).
Copy `spec.ts` from this directory and supply its TypeScript module-resolution
configuration if needed. The runner retains the packaged driver's Nix closure.
The runner freezes every supplied file and its hash before booting.

```sh
nix shell --inputs-from . nixpkgs#python3 -c python3 harnesses/hokum/run.py \
  --backend pipewire --bundle /absolute/path/to/bundle \
  --time-limit-fuzz 2m --time-limit-run 30s
```

Replay uses the original frozen bundle and `--replay RUN/artifacts/trace-0.bin`.
Historical instrumented bundles are retained as evidence, but the current
runner does not accept their old scene/audited-driver interface.

PipeWire mode provides real guest virtual input/output devices named
`bombadil-input` and `bombadil-output`. Native mute/volume/reset controls run
before fuzzing. No host device, desktop socket or host home is exposed.
`--backend mock` only disables the guest audio daemon; it does **not** inject
mock state into the application. The app still runs normally. No real BlueZ
daemon or virtual Bluetooth controller is provisioned yet.

The campaign runs as an unprivileged guest user, with private network/devices
and inaccessible system/user D-Bus sockets. Its separately created session bus
is private. The host Nix store is read-only; writable exchange shares are
disposable. This is isolation for UI testing, not a hostile-code sandbox.
Nix-linked dependencies embedded in the bundle are retained through their
closures; dynamically loaded Wayland/Vulkan/font libraries are supplied by
the VM. Requires x86_64 Linux, Nix and KVM.

## Scope and evidence

Rune's pinned build has no AT-SPI bridge. Actions therefore use screen
coordinates and keys, not internal semantic selectors. The initial spec
checks liveness, log collection and user-selected target error logs. It does
not pretend the former internal-tree/backend properties still apply.
Window readiness is not proof that all application pixels are ready, and
successful input delivery is not proof of the intended UI effect.

Runs live under `.state/hokum/run-*`, including frozen inputs, hashes, the
VM build expression, trace files, decoded states and screenshots. Full guest
`journal.log`, `pipewire-service.log` and driver stderr in `bombadil.log` are collected
even on failure. Exit 0 requires an engine success, a decodable trace and no
recorded violations. Exit 2 means recorded violations; status 125 means setup
or inspection did not complete. A short smoke is not campaign coverage.
