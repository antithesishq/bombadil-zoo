# Headplane browser harness

Runs Headplane, Headscale, Chromium and Bombadil in one disposable NixOS VM.
Requires Linux with access to `/dev/kvm`. The pinned nixpkgs currently supplies
Headplane 0.7.1 and Headscale 0.29.4; no production credentials or tailnet are used.

```sh
nix run .#fuzz-headplane
nix run .#fuzz-headplane -- --time-limit-fuzz 5m --time-limit-run 30s
nix run .#reproduce-headplane -- .state/headplane/fuzz-<timestamp>-<suffix>/artifacts/runs/0
nix build .#checks.x86_64-linux.smoke-headplane
```

Durations accept positive integers with `s`, `m` or `h` suffixes. The campaign
budget includes backend resets but not boot, seeding or the UI smoke test.
The test driver has a one-hour safety timeout for the entire invocation.
The runner stops on the first violation or error: exit 0 means no violation,
2 means a property violation, and other nonzero statuses indicate harness or
Bombadil errors. Unlike the terminal runners, this does not invoke the experimental
`browser fuzz` command or accept arbitrary Bombadil options. Native browser
fuzzing and shrinking do not reset the backend between sessions, so they cannot
replace this harness's snapshot/reset loop.

## Fixture and isolation

- Three users, two registered offline test machines (one expired), two pre-auth
  keys, an expiring API key, and an allow-all ACL policy stored in the database.
- A VM-local embedded DERP server, with no public DERP downloads. QEMU's user
  network is restricted; the services listen on loopback and no ports are
  forwarded to the host. There are no live Tailscale clients in this fixture.
- Headplane's Headscale configuration is read-only. Server-config editing,
  native restart integration, OIDC, the agent and browser SSH are not covered.
- Chromium runs without its own sandbox inside the disposable VM. Only the
  test driver's transfer directories and read-only Nix store are shared with
  the host; never point this harness at real data.

Each campaign first checks invalid/valid login and creates a user through the
UI, checks persistence after reload, and confirms the mutation through Headscale's
CLI. It then restores a quiescent snapshot of both services' state before every
Bombadil run, verifying that the smoke-test user is gone. Each run launches a
fresh browser profile. Parallel invocations use separate VMs and result paths.

The browser spec logs in with the fixture key whenever the login form appears,
then explores controls, inputs, navigation, reload and scrolling. Successive runs
cycle through 1280×800, 800×600 and 1440×900 viewports, saved for replay. The spec
checks uncaught exceptions, unhandled promise rejections, origin confinement,
and navigation responses below 500. It does **not** equate expected validation
messages or every console error with a bug, and navigation-status checks do not
cover every fetch response. The persistence check is a smoke test, not a general
oracle for every randomly generated mutation.

The Bombadil input is updated to include upstream fixes for replaying ordinary
buttons and custom actions; the previous pin could not replay the login flow.

## Results and replay

Results live in `.state/headplane/fuzz-<timestamp>-<suffix>/` (or `reproduce-…`):

```
driver.log             VM boot, fixture setup and test-driver diagnostics
driver-build           GC root retaining the original VM and its dependencies
request.json           campaign arguments / replay source
artifacts/
  status               campaign's Bombadil exit status
  builds.json          exact target, browser and Bombadil store paths
  headplane.yaml       rendered Headplane configuration
  fixture.tar          stopped-service state, including the test API key
  spec.ts              actual spec with the fixture key substituted
  driver               original test-driver executable used for replay
  machines.png         authenticated UI smoke-test capture
  users.png            persisted smoke-test mutation
  bombadil-<id>.log    actions and property/error diagnostics
  services-<id>.log    Headplane and Headscale journals
  runs/<id>/           trace.jsonl, screenshots/, viewport.json, status
```

All runs are retained, not just failures, so successful traces can also be
replayed. Browser screenshots and traces consume disk space; remove campaigns
you no longer need. Removing their `driver-build` roots also permits Nix to
garbage-collect the old VM builds. Artifacts contain fixture credentials and
typed values; campaign directories are private to the invoking user.

Replay boots the **original retained driver**, restores the saved backend state,
uses the saved spec, and starts a fresh browser. It never re-seeds with a new API
key. Keep the entire campaign directory on the same machine for replay.
Replay remains best-effort: browser timing, generated DOM identifiers and
wall-clock-dependent expiry can diverge. The fixture is a database snapshot,
not a frozen VM clock; keys can eventually expire.
In validation, an unlabelled Base UI button acquired a different generated ID
after logout/login, and Bombadil correctly stopped rather than matching a
different control. A saved fixture does not guarantee every trace can replay.

To inspect a trace interactively:

```sh
nix run .# -- browser inspect .state/headplane/fuzz-<timestamp>-<suffix>/artifacts/runs/0
```
