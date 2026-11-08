# bombadil-zoo

Fuzz harnesses for terminal, browser and Rune UIs, using [Bombadil](https://github.com/antithesishq/bombadil)'s
property-based testing. Everything runs through Nix.

| Harness | Target | Runs |
| --- | --- | --- |
| [`atuin`](harnesses/atuin) | [atuin](https://github.com/atuinsh/atuin)'s interactive search, over a seeded history database | in the Nix sandbox |
| [`btop`](harnesses/btop) | [btop](https://github.com/aristocratos/btop), in a PID namespace of its own | in the Nix sandbox |
| [`gitui`](harnesses/gitui) | [gitui](https://github.com/gitui-org/gitui), in a fresh copy of the shared git repository | in the Nix sandbox |
| [`headplane`](harnesses/headplane) | [Headplane](https://github.com/tale/headplane), against a seeded Headscale instance | in a disposable NixOS VM (Linux/KVM) |
| [`helix`](harnesses/helix) | [Helix](https://github.com/helix-editor/helix), on the shared source files | in the Nix sandbox |
| [`htop`](harnesses/htop) | [htop](https://github.com/htop-dev/htop), in a PID namespace of its own | in the Nix sandbox |
| [`k9s`](harnesses/k9s) | [k9s](https://github.com/derailed/k9s), against a throwaway kind cluster | on the host |
| [`lazygit`](harnesses/lazygit) | [lazygit](https://github.com/jesseduffield/lazygit), in a fresh seed repository | in the Nix sandbox |
| [`ncdu`](harnesses/ncdu) | [ncdu](https://dev.yorhel.nl/ncdu), scanning a fresh copy of the shared file tree | in the Nix sandbox |
| [`neovim`](harnesses/neovim) | [Neovim](https://github.com/neovim/neovim), `nvim --clean` on a seed of source and text files | in the Nix sandbox |
| [`rex-rune`](harnesses/rex-rune) | [Rex Linux](https://github.com/shuv1337/rex-rune), against a private Rex server through the in-process Rune driver | in the Nix sandbox (x86_64 Linux) |
| [`superfile`](harnesses/superfile) | [superfile](https://github.com/yorukot/superfile), in a fresh copy of the shared file tree | in the Nix sandbox |
| [`tig`](harnesses/tig) | [tig](https://github.com/jonas/tig), in a fresh copy of the shared git repository | in the Nix sandbox |
| [`yazi`](harnesses/yazi) | [yazi](https://github.com/sxyazi/yazi), in a fresh seed directory tree | in the Nix sandbox |

## Running

```sh
nix run .#fuzz-yazi                                         # 5 minute campaign
nix run .#fuzz-yazi -- --time-limit-fuzz 30m --parallelism 4 --swarm
nix run .#reproduce-yazi -- .state/yazi/runs/<ts>/trace-17.bin.zst
nix run .#shrink-yazi -- .state/yazi/runs/<ts>/trace-17.bin.zst --time-limit 2m
nix flake check                                             # specs, builds, smoke campaigns
```

Terminal campaigns default to **one worker**. Use `--parallelism N` to change
the number of workers. CPU affinity is separate: for example,
`ZOO_CPUS=4-7 nix run .#fuzz-yazi -- --parallelism 4` pins the campaign and its
target processes to CPUs 4 to 7. Only parallelize targets whose state is isolated;
the host-run k9s harness shares its cluster.

Headplane runs one browser worker inside its own VM. Its arguments, fixture reset,
replay directory and artifacts differ from the terminal harnesses; see
[its instructions](harnesses/headplane/README.md).

The [Rex Rune example](harnesses/rex-rune/README.md) uses a separate pinned
`bombadil-drivers` input and experimental external engine. It requires a
host-installed Rex binary; follow its setup instructions before running
`nix run .#fuzz-rex-rune`. Existing terminal/browser engine pins are unchanged.

Every harness has `fuzz-<name>` and `reproduce-<name>`. Terminal results go to
`.state/<name>/runs/<timestamp>/`:

```
status        bombadil's exit status
violations    violated properties and their run IDs
crashes       distinct crash messages from the target's stderr
trace-<id>.bin.zst  binary trace, kept for property violations and identified crashes
stderr/<run-id>-<pid>  the target's stderr, per process
spec/         the spec the campaign ran with, used by reproduce-<name>
```

A full campaign's traces run to hundreds of gigabytes, which is why only
failing runs keep theirs. Replays need the spec a trace was recorded with,
which is why every campaign keeps a copy.

`nix run .# -- <args>` runs Bombadil itself.

## Bombadil controls

Bombadil is pinned to a revision of upstream `main`, including binary traces.
Terminal fuzz apps forward their arguments to
`bombadil terminal fuzz`; useful controls include:

| Option | Purpose / default |
| --- | --- |
| `--time-limit-fuzz 30m` | Campaign budget; default 5m |
| `--time-limit-run 20s` | Per-run budget; default 10s |
| `--parallelism 4` | Concurrent workers; default 1 |
| `--swarm` | Vary the enabled action categories between runs |
| `--columns 120 --rows 40` | Initial terminal size; default 100×40 |
| `--scrollback-lines-max 200` | Retained scrollback; default 100 lines |
| `--quiescence-timeout-ms 20` | Wait longer for terminal output to settle; default 5ms, at a throughput cost |

Do not use `--exit-on-violation` to stop a native fuzz campaign: Bombadil accepts
but ignores it in fuzz mode. Fuzzing can exit successfully despite violations;
read `violations` and `bombadil.log`, not just the exit status. There is no public
random-seed option. The runner's Nix `seed` parameter only makes a distinct build;
it does not make random exploration deterministic.

### Minimize a terminal failure

Every **sandboxed terminal** harness provides `shrink-<name>`. It decompresses the
input, uses the campaign's saved spec when available, and runs native
`terminal shrink` inside the same Nix sandbox with a fresh target per trial.
Options after the trace go to Bombadil: use `--property NAME` when multiple
properties failed, `--time-limit 2m` to bound the search, and `--parallelism N`
only for isolated trials. Calibration defaults to 3 runs and confirmation to
at most 5 (`--calibration-runs`, `--confirmation-runs-max`).

Results go to `.state/<name>/shrinks/<timestamp>/`: `bombadil.log` contains the
action-count reduction and reproduction counts; `status` records whether
shrinking succeeded. The counterexample remains a failure, not a passing test.
The minimized trace is `trace.bin`; replay it with `reproduce-<name>`.
The result also keeps `spec/`, so another shrink uses the same specification.
Reproduction and shrinking are experimental and cannot repair a flaky trace.

Inspect binary traces with `bombadil trace <file> --json` or `--screen`.
Decompress `.zst` files first. Old JSONL traces are not compatible with this pin.

There is no shrink wrapper for k9s or Headplane: native shrinking creates many
sessions without resetting a shared backend between trials. In particular,
Headplane must keep its VM snapshot/reset loop rather than switch to native
`browser fuzz` just because that command is now visible in `--help`.

Use `nix run .# -- terminal --help` or `browser --help` to explore all commands;
each subcommand has its own `--help`. Browser-only controls include `--allow-url`,
`--header`, `--cookie`, instrumentation, permissions and virtual time. They are
not forwarded by the Headplane runner: changing them without saving the same
settings for replay would invalidate comparisons. The browser inspector supports
`--no-open --port N`, but binds all network interfaces; do not expose traces or
fixture credentials on an untrusted network.

## Layout

```
flake.nix               inputs and wiring
nix/
  harnesses.nix         imports every harness under harnesses/
  zoo/                  the library harnesses get as `zoo`
    sandboxed.nix       runner: campaigns as Nix builds
    host.nix            runner: campaigns on your machine
    scripts.nix         pruning, reports, launchInCopy
  checks.nix            spec type-checking
  devshell.nix          development shells
lib/spec/common.ts      helpers shared by the specs
harnesses/<name>/
  default.nix           how to build and launch the target
  spec.ts               properties and actions
  patches/              fixes carried while they're pending upstream
```

The k9s harness builds k9s `master` at a pinned revision, so its patches
are the fixes not merged yet. Drop a patch when its fix lands and bump the
revision. The yazi harness patches the release in nixpkgs.

## Adding a harness

Create `harnesses/<name>/default.nix` and `harnesses/<name>/spec.ts`. The
flake picks up the directory automatically.

`default.nix` takes `{ pkgs, bombadil, zoo }`, writes a `launch` script that
starts one instance of the target, and hands it to a runner:

- `zoo.sandboxed { name, launch, inputs }` runs each campaign as a Nix
  build: no network and no access to your home directory. Use it for
  anything that can run commands or change files, e.g. a file manager's
  shell prompt or a git client.
- `zoo.host { name, launch, setup }` runs on your machine, for targets that
  need real resources, like k9s and its cluster. `setup` runs first with
  `$state` set to `.state/<name>`; use it to keep the target away from your
  real config.

`launch` is called as `launch <run dir>`. It should give every run a fresh
copy of any state the target changes, and send stderr to
`<run dir>/stderr/<pid>` and to the terminal with `${zoo.teeStderr}`, so the
spec sees crash messages on screen. For targets that work on files,
`zoo.launchInCopy { name, seed, command, prepare, env }` does all of that:
it starts `command` in a fresh copy of the `seed` derivation, after running
`prepare` there for entries a store path can't hold, like FIFOs. Both runners
accept `devShell`, an attribute set passed to `pkgs.mkShell`: for example,
`devShell.packages = [ pkgs.ncdu ];`. Custom `shellHook`s go in that same
attribute set. Add `packages` for target builds by merging them into the
runner's result.

`spec.ts` uses `lib/spec/common.ts`: `noCrashText` for the target's crash
messages, `neverStuckBlank`, `keys` and `resize` for actions, and
`pauseAfterEscape` around the action generator. Without that pause, an Esc
followed immediately by another key reads as Alt+key, which makes traces
replay differently from how they were recorded.

`nix develop` gives a shell with every harness's tools and links the
Bombadil types into `node_modules/` for editors; `nix develop .#<name>`
gives just one harness.
