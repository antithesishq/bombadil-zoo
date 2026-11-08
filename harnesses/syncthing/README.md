# Syncthing browser harness

Fuzzes the real Web UI served by the pinned nixpkgs `syncthing` package
(currently 2.1.7). Syncthing, Chromium and Bombadil run inside one disposable
NixOS VM with **2 virtual cores**. Requires Linux and `/dev/kvm`.

```sh
nix run .#fuzz-syncthing
nix run .#fuzz-syncthing -- --time-limit-fuzz 5m --time-limit-run 20s --parallelism 2 --swarm
nix run .#fuzz-syncthing -- --width 800 --height 600
nix run .#fuzz-syncthing -- --chrome-virtual-time-policy Pause
nix run .#reproduce-syncthing -- .state/syncthing/fuzz-<timestamp>-<suffix>/artifacts/trace-0.bin
nix build .#checks.x86_64-linux.smoke-syncthing
```

Durations accept positive integers with `s`, `m` or `h` suffixes. The test
driver has a one-hour safety timeout for the whole invocation, including boot.
Campaigns default to Chrome's `PauseIfNetworkFetchesPending` virtual-time policy.
Override it with `--chrome-virtual-time-policy Advance` or `Pause`; the resolved
choice is saved in `request.json` and reused for replay.

## Fixture and isolation

The VM starts with a fresh, isolated home, configuration and SQLite database.
Syncthing generates a new throwaway device identity and API key; there are no
real credentials, configured remote devices or shared host files. A `zoo-sample`
folder labelled **Zoo Samples** contains a readme, CSV inventory and Unicode
text so scanning and folder statistics have meaningful input.

QEMU networking is restricted and no ports are forwarded. The fixture also
disables synchronization listeners, local/global discovery, relays, NAT,
STUN, usage reporting, crash reporting and automatic upgrades. Browser actions
can change only disposable VM state. The service is configured to start again
after both Restart and Shut Down so later browser runs remain useful.

Campaigns use native `bombadil browser fuzz`. Every run gets a fresh browser
profile, while all workers in one VM share the Syncthing process, configuration
and folder. Consequently a mutation made by one run can affect later runs;
parallel invocations of the app use separate VMs and result paths. This is not
a per-run backend reset mechanism.

The spec waits for rendered dashboard state, then combines Bombadil's normal
click, input, scroll and navigation generators with bounded actions that expand
the first folder, resume or rescan it, and open its existing-folder settings.
The latter visits General, Sharing and File Versioning without saving, leaving
generic input actions to mutate the fixture's forms. These deliberately cover
per-folder controls that generic clicking rarely reaches in sequence. Opening
folder settings is intentional; these actions do not open nested dialogs.

The spec checks UI startup, reload recovery, origin confinement, uncaught
exceptions, unhandled promise rejections and navigation HTTP errors. Expected
settings validation and rejected REST requests are not themselves violations.
A parallel worker can restart Syncthing while another reloads; Chrome's internal
`chrome-error://chromewebdata/` page is therefore not treated as remote
navigation, and the reload-recovery property still requires the UI to return.

## Smoke check and results

Before fuzzing, the smoke check loads the actual Angular Web UI, verifies the
seeded folder and three-file local state, clicks **Rescan All** and requires a
successful scan API response, then opens **Settings**, switches to the GUI tab,
checks the populated fields and closes the dialog. The Nix smoke check also runs
a short native fuzz campaign and checks that its trace reached a rendered
dashboard.

Results go to `.state/syncthing/fuzz-<timestamp>-<suffix>/`:

```
driver.log             VM startup and test-driver diagnostics
driver-build           GC root retaining the original VM build
request.json           campaign arguments or replay request
artifacts/
  status               0: no violations, 2: violations, other: harness error
  violations           violated property names and their trace filenames
  trace-<id>.bin       binary traces with embedded screenshots
  spec.ts              exact specification used by the campaign
  request.json         resolved arguments, including virtual-time policy
  builds.json          exact Syncthing, Chromium and Bombadil builds/versions
  driver               original test driver used for replay
  bombadil.log         native fuzz progress and diagnostics
  server.log           Syncthing and configuration-service journals
  dashboard.png        seeded dashboard smoke-test capture
  settings.png         populated GUI-settings smoke-test capture
```

All traces are retained, not only failures. Remove old campaigns and their
`driver-build` roots when no longer needed; screenshots can use substantial
disk. Native fuzz can exit successfully despite violations, so the runner reads
trace metadata and returns status 2 when `violations` is non-empty.

Replay boots the original retained driver and uses the saved spec, viewport and
virtual-time policy with a fresh VM, backend and browser. Keep the campaign
directory on the same machine. Replay is best-effort: asynchronous scanning,
service restarts, wall-clock state and generated DOM identifiers can diverge.
Reproduction results contain `trace.bin` instead of numbered fuzz traces. There
is no shrink wrapper.
