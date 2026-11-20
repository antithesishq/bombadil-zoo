# llama.cpp WebUI harness

Fuzzes the [llama.cpp WebUI](https://llama.app/docs/webui) served by the pinned
nixpkgs `llama-cpp` package (currently 0.8.0). Runs the real CPU-only server,
Chromium and Bombadil inside a disposable NixOS VM. Requires Linux and `/dev/kvm`.

```sh
nix run .#fuzz-llama-webui
nix run .#fuzz-llama-webui -- --time-limit-fuzz 5m --time-limit-run 20s --parallelism 2 --swarm
nix run .#fuzz-llama-webui -- --width 800 --height 600
nix run .#fuzz-llama-webui -- --chrome-virtual-time-policy Pause
nix run .#reproduce-llama-webui -- .state/llama-webui/fuzz-<timestamp>-<suffix>/artifacts/trace-0.bin
nix build .#checks.x86_64-linux.smoke-llama-webui
```

Durations accept positive integers with `s`, `m` or `h` suffixes. The test
driver has a one-hour safety timeout for the whole invocation, including boot.

Campaigns default to Chrome's `PauseIfNetworkFetchesPending` virtual-time policy
to advance timer-driven UI work between network fetches. Override it with
`--chrome-virtual-time-policy Advance` or `Pause`; the choice is saved with the
campaign and reused for replay.

## Fixture and isolation

The router exposes upstream's tiny `stories260K-f32.gguf` test model as
`zoo-tiny`, pinned by Hugging Face revision and content hash. No account, GPU or
large model download is needed. The tiny model exercises real streaming
inference, not answer quality. It has no vision, audio or tool-calling
capability. The router loads one model at a time and uses ChatML, two inference
slots, a 2048-token context shared between them, and at most 64 generated tokens
per request. Settings can still provoke validation errors.

The model is fetched at build time and linked into an isolated router directory.
The VM runs offline with restricted QEMU networking, no forwarded ports, no real
credentials, no MCP configuration and no shared home or model cache. UI actions
can change only disposable VM state.

Campaigns use native `bombadil browser fuzz`. Each run starts a fresh browser
profile, so conversations in IndexedDB and UI preferences do not carry between
runs. The router and its model-loading state are shared within each VM.
Parallel invocations use separate VMs and result paths.

The spec waits for the application to load before exploring. It combines
generated clicks, input, scrolling and navigation with generated chat text
(ASCII, Markdown symbols and any printable Unicode) typed into the composer and
sent with Enter. It checks UI startup, reload recovery, generation completion,
uncaught exceptions, unhandled promise rejections, navigation HTTP errors and
origin confinement. It does not treat handled form/API validation as
a bug or claim coverage of multimodal rendering, external MCP services or model
quality.

## Checks and results

The smoke check sends a real streaming chat request, waits for an answer,
reloads the conversation and checks that both turns persisted, then opens
Settings. It also runs native fuzzing and verifies the trace reached a loaded UI.

Results go to `.state/llama-webui/fuzz-<timestamp>-<suffix>/`:

```
driver.log             VM startup and test-driver diagnostics
driver-build           GC root retaining the original VM build
request.json           campaign arguments or replay request
artifacts/
  status               0: no violations, 2: violations, other: harness error
  violations           violated property names and their trace filenames
  trace-<id>.bin       binary traces with embedded screenshots
  spec.ts              the specification used by this campaign
  request.json         original arguments, including viewport size
  builds.json          exact server, model, Chromium and Bombadil paths
  driver               original test driver used for replay
  bombadil.log         native fuzz progress and diagnostics
  server.log           inference server journal
  chat.png             persisted conversation smoke-test capture
  settings.png         settings smoke-test capture
```

All traces are retained. The runner reads their violations because native fuzz
can exit successfully despite finding failures. Remove old campaigns and their
`driver-build` roots when no longer needed; screenshots can use substantial disk.

Replay uses the retained driver, model, spec and viewport, with a fresh browser.
Keep the campaign directory on the same machine. Replay is best-effort: inference
timing, sampling and generated DOM identifiers can diverge. Reproduction results
contain `trace.bin` instead of numbered fuzz traces. There is no shrink wrapper.
