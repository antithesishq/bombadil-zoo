# Gitea browser harness

Fuzzes the real nixpkgs `gitea` server, Chromium and native Bombadil browser
fuzzing in one disposable NixOS VM. The VM has exactly two virtual cores, uses a
disposable SQLite database, and requires Linux with `/dev/kvm`.

```sh
nix run .#fuzz-gitea
nix run .#fuzz-gitea -- --time-limit-fuzz 5m --time-limit-run 20s --parallelism 2 --swarm
nix run .#fuzz-gitea -- --width 800 --height 600
nix run .#fuzz-gitea -- --chrome-virtual-time-policy Pause
nix run .#reproduce-gitea -- .state/gitea/fuzz-<timestamp>-<suffix>/artifacts/trace-0.bin
nix build .#checks.x86_64-linux.smoke-gitea
```

Durations accept positive integers with `s`, `m` or `h` suffixes. The test driver
has a one-hour safety timeout for the whole invocation, including VM boot.

Campaigns default to Chrome's `Advance` virtual-time policy because the pinned
Chromium 157 and Bombadil 0.7.10 stall on the navigation immediately after login
with `PauseIfNetworkFetchesPending`. The network-gated policy is still available
for experiments, but the harness requires an authenticated page so stalled
campaigns fail instead of looking useful. Override it with `--chrome-virtual-time-policy Pause` or `PauseIfNetworkFetchesPending`. The resolved choice and all
other arguments are saved in `artifacts/request.json` and reused for replay.

## Fixture and isolation

The service listens only on `127.0.0.1:3000`, with `INSTALL_LOCK = true`, SSH and
registration disabled, sign-in required, mail and Actions disabled, and remote
avatars turned off. QEMU networking is restricted and no ports are forwarded to
the host. There are no external services or real credentials.

The CLI creates the non-admin fixture user `fixture` with the throwaway password
`zoo-fixture-password`. The API creates `fixture/zoo-repo`; a real Git push adds
Markdown documentation and a Python source file. Two issues (one open and one
closed) provide issue-list and issue-detail state. These credentials and all
mutations are confined to the disposable VM.

The smoke check logs in through the actual Web UI, verifies the signed-in user,
opens the seeded repository and its rendered README, checks the documentation
and source entries, opens the seeded issue, and inspects repository settings.
It then runs a short native fuzz campaign and checks that its trace contains the
custom login action and an authenticated state.

## Fuzzing and properties

Native `browser fuzz` starts at `/user/login`. Each run has a fresh browser
profile, so the spec submits the fixture login whenever the login form appears,
including after an exploratory logout. The server, database and repositories are
shared by workers within one VM; actions can mutate them. Separate invocations
get separate VMs and result paths.

Exploration combines Bombadil's normal clicks, keyboard input, history, reload,
scrolling and waiting with deterministic navigation to the seeded repository,
file and commit views, issue list/detail/new forms, and repository settings.
Issue forms also receive deterministic titles and Markdown/Unicode content;
native submit clicks exercise real comment and issue creation transitions.
Navigation uses a temporary link followed by a native click, avoiding a custom
action whose execution context is destroyed by its own navigation. Auxiliary
pages without Gitea's navbar recover to the repository instead of waiting for an
impossible selector. Properties check uncaught JavaScript exceptions, unhandled
promise rejections, origin confinement, UI startup and reload recovery, and
navigation responses below 500. Expected validation errors and 4xx responses
are not treated as Gitea failures. This does not provide an oracle for arbitrary
repository mutations, Git protocol behavior, mail, federation, Actions, OAuth or
administration. Parallel workers exercise Gitea's real handling of shared state,
not isolated per-run backend snapshots.

## Results and replay

Results go to `.state/gitea/fuzz-<timestamp>-<suffix>/`:

```
driver.log             VM startup and test-driver diagnostics
driver-build           GC root retaining the original VM build
request.json           campaign arguments or replay request
spec.ts                specification copied into the campaign
artifacts/
  status               0: no violations, 2: violations, other: harness error
  violations           violated property names and trace filenames
  trace-<id>.bin       binary traces with embedded screenshots; all retained
  spec.ts              actual specification used by Bombadil
  request.json         resolved arguments, including virtual-time policy
  builds.json          exact Gitea, Chromium and Bombadil store paths
  gitea.ini            effective configuration with generated secrets redacted
  repository.json      seeded repository API response
  issue.json           seeded open-issue API response
  closed-issue.json    seeded closed-issue API response
  driver               original test driver used for replay
  bombadil.log         native fuzz progress and diagnostics
  server.log           Gitea journal
  repository.png       authenticated seeded-repository smoke capture
  issue.png            seeded issue smoke capture
  settings.png         repository-settings smoke capture
```

All traces are retained and can consume substantial disk space. Remove old
campaign directories and their `driver-build` roots when no longer needed.
Native fuzz may exit zero despite violations; the runner inspects every trace
and returns status 2 when any property failed. It also requires an authenticated
page state, so a login-only or stalled campaign fails instead of looking useful.

Replay uses the retained driver, exact spec, viewport and virtual-time policy,
re-seeds the same fixture and starts a fresh browser. Keep the campaign directory
on the same machine. Replay is best-effort because prior runs can mutate the
shared server, random exploration order differs, and generated DOM state and
wall-clock behavior can diverge. There is no shrink wrapper.

Inspect a trace with:

```sh
nix run .# -- trace --json .state/gitea/fuzz-<timestamp>-<suffix>/artifacts/trace-0.bin
```
