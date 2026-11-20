# Grok Build TUI

Runs the unmodified **Grok Build 1.0.77** vendor binary against a private mock
inference server. The version overrides nixpkgs' 1.0.70 package. Download hashes
match [Homebrew's release update](https://github.com/Homebrew/homebrew-cask/pull/300355).
The binary identifies itself as `grok 1.0.77 (50ca579fa996)` on x86_64 Linux.

## Run

```sh
nix run .#fuzz-grok-build -- --time-limit-fuzz 5m --time-limit-run 15s --parallelism 2 --swarm
nix run .#reproduce-grok-build -- .state/grok-build/runs/<timestamp>/trace-<id>.bin.zst
nix run .#shrink-grok-build -- .state/grok-build/runs/<timestamp>/trace-<id>.bin.zst --time-limit 2m
nix build .#checks.x86_64-linux.mock-grok-build
```

Each run gets a fresh home, config, project directory, and loopback server on an
OS-assigned port. Runs use the Nix sandbox: Grok can change disposable files but
cannot access your home or connect to external APIs. No real API key is needed.
The package permits only Grok Build's unfree redistributable binary license;
it does not enable unfree packages globally.

## Mock responses

This is **endpoint redirection**, not HTTPS interception. Grok's supported custom
model configuration points Chat Completions requests at the fixture server.
It also redirects the model-list and auxiliary proxy URLs to loopback. Unknown
routes return 404; auxiliary Responses API calls are not simulated. The Nix
sandbox blocks external traffic even if the app tries another endpoint.

The initial prompt requests a streamed Markdown response. Fuzz actions submit
these markers to select other fixtures:

| Prompt | Response |
| --- | --- |
| `zoo:markdown` | SSE chunks containing Markdown, code, a table, math, and Unicode |
| `zoo:slow` | The same response with slower chunks, for cancellation and queued input |
| `zoo:rate-limit` | HTTP 429 with an API error body |
| `zoo:server-error` | HTTP 500 with an API error body |
| `zoo:malformed` | Invalid JSON in an SSE event |
| `zoo:disconnect` | A partial response without a finish event or `[DONE]` |
| `zoo:reasoning` | Split reasoning deltas followed by the Markdown response |
| `zoo:tool-call` | Split deltas for a sandboxed `run_terminal_command` call, then a Markdown follow-up |

Other prompts get a fixture chosen by a hash of their text (tool calls only when
the request offers tools), so generated prompts reach every fixture and a given
prompt always gets the same one. Matching uses the latest user message,
not earlier history. A tool result completes the turn with Markdown instead of
issuing the same call again. Grok can retry errors and incomplete streams; a
retry is not itself a harness failure.

Fixture names are in `mock.py` (`FIXTURES` and `TOOLS`): Markdown stress
cases (`zoo:mermaid`, `zoo:table`, `zoo:nested`, `zoo:unicode`, `zoo:code`,
`zoo:long`), stream faults (`zoo:truncated`, `zoo:html-error`), and one
`zoo:tool-*` prompt per tool with a visible surface (`run_terminal_command`,
`write`, `search_replace`, `todo_write`, `ask_user_question`, plan mode).

The campaign generates only input a person at a working terminal can produce, as
a weighted mix: mock prompts and tool calls, slash commands with valid and
invalid arguments, shell mode, completion popups, card answers, navigation and
line editing, key chords, Unicode text, bracketed pastes, clicks, wheel, drags
and focus reports inside the window, Ctrl+C, and resizes between 40x12 and
250x70. Unsolicited terminal replies (cursor, color and device reports) are not
generated. Grok starts with `--trust` in a seeded git repository with awkward
filenames.

Properties check startup, blank-screen stalls, panic text and backtrace
frames, exit codes, and fatal signals. SIGINT is allowed because the campaign
deliberately types Ctrl+C. The properties do not assert model quality or
complete API recovery. The wrapper preserves the child's fatal signal so a
target crash cannot become a normal wrapper exit.

`ZOO_GROK_VERSION=1.0.87` runs the alpha channel binary instead of stable
1.0.77 (x86_64 Linux only).

## Results and checks

Results use the shared terminal layout under `.state/grok-build/runs/`.
Inspect `violations` and `crashes` as well as `status`: native fuzz mode can exit
successfully despite property violations. The stderr files retain `zoo-mock:`
request/scenario records alongside Grok's output. Only failing traces survive
campaign pruning. Replay uses the saved spec and starts a fresh mock server;
network timing and retries can still make replay nondeterministic.

### Confirmed tiny-terminal panic

The expanded campaign in `.state/grok-build/runs/20261112-233232/` retained 26
SIGABRT occurrences of one Ratatui buffer-indexing bug. The minimized
`noPanic` trace in `.state/grok-build/shrinks/20261112-234340/trace.bin` reduces
run 83 from 115 actions to these three, starting after the initial Markdown
reply has rendered:

1. Resize to 19 columns × 2 rows.
2. Paste `@hello.py` using bracketed paste.
3. Resize to 114 columns × 48 rows.

Grok aborts with `Rect { x: 0, y: 0, width: 19, height: 2 } but index is (1, 2)`
in `ratatui-0.29.0/src/buffer/buffer.rs:253`. Reproduce it with:

```sh
nix run .#reproduce-grok-build -- .state/grok-build/shrinks/20261112-234340/trace.bin
```

The original calibrated 3/3, the minimized trace confirmed 2/2, and three
additional replays all produced the same dimensions. A direct PTY control matrix
confirmed that file-reference completion is the trigger: all 6/6 runs with the
paste crashed, versus 0/6 without it. The final resize is unnecessary for the
crash (3/3 crashed without it); it only exposes the panic for `noPanic`.
An 80-case clean-state sweep crashed only at 2 rows, for all seven tested widths
from 7 through 100; widths 1, 4, and 5 and heights 1 and 3–8 did not crash.
The retained full backtraces have addresses but no function names because the
vendor binary is stripped. No upstream source fix has been made.

The earlier, timing-sensitive history-overlay failure has its original trace,
a 21-action reduced reproducer, matching specs, stderr, and investigation record
preserved in [`traces/history-overlay-panic/`](traces/history-overlay-panic/README.md).

`mock-grok-build` checks every fixture protocol, wrapper signal handling, and
fatal-signal propagation. The launcher sets `RUST_BACKTRACE=full` for retained
panic diagnostics. The check also runs the real TUI in the sandbox and requires
`ZOO_MOCK_OK` to appear on its terminal screen. This catches a harness that starts
the UI but never receives a mock completion. `smoke-grok-build` runs the normal
fuzz spec, and the shared `specs` check type-checks it.
