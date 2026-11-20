# Vercel fx

Pinned official fx v0.0.17 binaries, verified against the release checksums.
Each target gets a fresh project, home directory, and loopback mock provider
inside the Nix sandbox. No login, real credentials, or model billing is needed.
The mock streams Markdown, Unicode, tables, long and slow replies, reasoning,
usage trailers, fragmented SSE, malformed/truncated streams, and HTTP errors.
It also streams tool calls into fx's real tool executor, permission UI, and
question cards. It does not use real inference. A prompt with a `zoo:<name>`
marker gets that fixture; any other prompt gets one chosen by a hash of its
text (tool calls only when the request offers tools), so generated prompts
reach every fixture.

```sh
nix run .#fuzz-fx -- --time-limit-fuzz 5m --time-limit-run 10s --parallelism 1
ZOO_FX_UNCONSTRAINED=1 nix run .#fuzz-fx -- --time-limit-fuzz 5m --time-limit-run 10s --parallelism 1
nix build .#checks.x86_64-linux.mock-fx .#checks.x86_64-linux.specs
```

`nix build .#vercel-fx-patched` builds the same source revision with the local
`command-approval-zero-width.patch` and `ask-zero-footer-layout.patch`. They route
command approvals that cannot fit inline to the review screen, and share one
footerless-layout constructor that avoids unsigned subtraction. The official
release binary remains the fuzz target; the patched package is only for local
verification.

Normal mode starts at 100×40 and resizes within 40–250 columns and 12–70 rows.
Unconstrained stress mode broadens resizing to 1–500 columns and 1–150 rows,
with extra weight on 1–4-cell sizes. All generated input represents user
actions; synthetic terminal-status replies are excluded. The sandbox remains
enabled. Neither mode deliberately quits or suspends the target.

The spec's properties are application-independent: fx starts, never prints a
Zig panic or safety failure, never dies on a signal, never leaves a blank
screen and exits cleanly. Its actions are a weighted mix of what a person can
do at a terminal: mock prompts and tool calls, slash commands with valid and
invalid arguments, completion popups, card answers, navigation and line
editing (including modified arrows), Ctrl chords, Unicode text, bracketed
pastes, clicks, wheel, drags and focus reports inside the current window, and
resizes.

Tool prompts cover file and shell operations, glob/grep, a seeded skill,
`ask_user_question`, and malformed calls. MCP calls use the populated `zoo`
server and the shared `lib/mcp_mock` stdio package. Shell sessions capture real
IDs for input and stop, and a missing `read_tool_result` handle covers recovery
guidance. `batch` requests a read and shell call together; `chain` writes,
reads, then edits; `diff` writes 80 long Unicode lines.
Arguments always stream in chunks. Valid plans advance from tool results in the
current user turn and terminate with `ZOO_TOOL_DONE`, including after denial
or tool errors; malformed streams exercise their error paths instead. Earlier
turns do not suppress new calls. Paths and shell commands are fixed fixture
values. Shell fixtures use a clean Bash PTY because the Nix sandbox has no
`/bin/bash`.

Real RGBA and palette PNGs exercise attachment capture, placeholder editing,
and `image_url` serialization. A truncated PNG and unknown image placeholders
cover rejection paths. The seeded `zoo-review` skill exercises catalog pickers,
`$` completion, and skill loading through `toolbox`.

The `mock-fx` check runs the real binary, checks file and shell results, and
resumes a session for another tool turn. It verifies interleaved tools, extreme
offsets, reasoning and fragmented SSE, and the provider's received image parts.
It also opens a real terminal, waits for file approval, resizes it, and checks
that approval writes the file while denial preserves its original contents.
Direct user-navigation checks open help, settings, model, resume, populated MCP,
usage, status line, workspace, permissions, effort, skills, agents, fork, and
image screens, plus the Ctrl+P model picker. Image sequences preserve pending
attachments instead of clearing them with Ctrl+U. Question checks cover
21-question, seven-option, and case-insensitive duplicate-label rejection.

Source-guided cases target `gateway/chat_completions_protocol.zig`'s reducer,
`core/agent/assistant_presentation.zig`'s streaming Markdown parser,
`tools/agent/ask_user_question.zig` and `core/agent/question_prompt.zig`,
`core/images/`, and the transcript painters. `noPanic` and `noFatalSignal`
cover Zig safety failures, fatal signals, and the observed
`invalid transcript transition` and zero-width approval exits.

Sessions are created through ordinary fx commands. No synthetic session logs,
counter overflows, or terminal-status replies are injected.

Direct PTY probes also confirmed `integer overflow` at both 1×1 and 2×80 in
the zero-footer `fx ask` frontend (`ui/terminal/terminal.zig`). Unrealistic
`u16`-sized terminal dimensions are excluded from the generated stress cases.
With `ask-zero-footer-layout.patch`, the 1×1, 2×80, normal-size, and
resize-to-1×1 probes all exit successfully.

These are input-coverage targets, not measured source-code coverage.
Authentication changes, new fx instances, and deliberate quit/suspend actions
are excluded.

Results live under `.state/fx/runs/`. The selected mode is saved in `spec/`;
`reproduce-fx` and `shrink-fx` reuse it without the environment variable.
Check `violations`, `crashes`, and `bombadil.log`, not only the exit status.
