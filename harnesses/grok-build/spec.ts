// Grok Build is a coding-agent TUI. The mock server (mock.py) maps every
// prompt to one of its fixtures by a hash of the text, so generated prompts
// reach replies that render, stream slowly, fail or arrive malformed, and
// tool calls that open permission, question, todo, diff and plan cards. The
// properties are Grok-independent: it starts, never panics or dies on a
// signal other than Ctrl+C, never leaves a blank screen and exits cleanly.
// Every action is generated: text, prompts, slash and shell commands,
// pastes, keys, clicks and sizes.
import { always } from "@antithesishq/bombadil";
import { ActionGenerator } from "@antithesishq/bombadil/actions";
import { type ActionTemplate, extract, weighted } from "@antithesishq/bombadil/terminal";
import { CharSets, typeFromSet } from "@antithesishq/bombadil/terminal/defaults/actions";
import { noCrashText, pauseAfterEscape, resize, startsShowing } from "../../lib/spec/common.ts";
export { exitSuccess } from "@antithesishq/bombadil/terminal/defaults/properties";
export { neverStuckBlank } from "../../lib/spec/common.ts";

// Properties

export const startsUp = startsShowing(/Grok|Zoo Mock|zoo-mock/);

// Ctrl+C is one of the actions. Any other signal is a crash.
const exitSignal = extract((state) => state.exitStatus?.signal ?? null);
export const noFatalSignal = always(
  () => exitSignal.current == null || exitSignal.current === "Interrupt",
);

// With RUST_BACKTRACE=full the frames scroll the "panicked at" line off the
// screen at once, so match the frames too.
export const noPanic = noCrashText(
  /0x[0-9a-f]{8,16} - <unknown>|stack backtrace:|panicked at|fatal runtime error:|stack overflow|RUST_BACKTRACE|index out of bounds|is not a char boundary|attempt to \w+ with overflow|called `(Option|Result)::unwrap/,
);

// Actions

// Types a string generated from a regular expression (Rust syntax).
const typed = (regexp: string): ActionTemplate => ({ TypeText: { Regexp: regexp } });

// Ctrl+U clears the prompt first, so the text is not appended to a draft.
const clear = "\x15";

// Prompts, slash commands and shell commands with generated names and
// arguments, in ASCII or any printable Unicode.
const prompts = weighted([
  [3, typed(`${clear}[ -~]{1,80}\r`)],
  [1, typed(`${clear}\\PC{1,200}\r`)],
]);
const commands = weighted([
  [3, typed(`${clear}/[a-z][a-z-]{0,14}( [ -~]{0,40})?\r`)],
  [1, typed(`${clear}![ -~]{0,40}\r`)],
]);

// A mode prefix and a few characters, leaving Grok's own completion popup
// open for commands, files and shell history; the keys below pick from it.
const completions = typed(`${clear}[/@!#][a-z/.]{0,3}`);

// Digits and letters answer cards and drive pickers and the transcript.
const answers = typed("[0-9a-zA-Z]");

// Arrows, Home/End, PageUp/PageDown, Tab, Shift+Tab, Enter, Space, Escape,
// Backspace and Delete, with and without Shift, Alt and Ctrl.
const navigate = weighted([
  [6, typed("\x1b\\[[ABCDHF]|\x1b\\[[56]~|[\t\r \x1b\x7f]|\x1b\\[Z|\x1b\\[3~")],
  [2, typed("\x1b\\[1;[2-8][ABCDHF]|\x1b\\[[356];[2-8]~")],
]);

// Ctrl and Alt chords and function keys. Ctrl+D and Ctrl+Q quit and Ctrl+Z
// suspends, so they are left out; Ctrl+C has its own, lower weight.
const chords = typed("[\x01\x02\x05-\x10\x12-\x19\x1c-\x1f]|\x1b[a-z\x7f]|\x1bO[PQRS]|\x1b\\[(1[5789]|2[0134])~");

// Bracketed pastes of any text, including newlines and control characters.
const paste = typed("\x1b\\[200~(?s:.){0,3000}\x1b\\[201~");

const text = weighted([
  [5, typeFromSet(CharSets.ASCII_PRINTABLE)],
  [2, typeFromSet(CharSets.UNICODE_SAFE)],
]);

// Window sizes from a split pane (40x12) to a maximized window on a large
// monitor (250x70).
const sizes = resize([40, 250], [12, 70]);

// Clicks and wheel land inside the window as it currently is; focus leaves
// and returns.
const size = extract((state) => state.grid.size);
const mouse = new ActionGenerator<ActionTemplate>(() => {
  const { columns, rows } = size.current ?? { columns: 80, rows: 24 };
  return weighted([
    [4, { Click: { column: [0, columns - 1], row: [0, rows - 1] } }],
    [2, { ScrollUp: {} }],
    [2, { ScrollDown: {} }],
    [1, typed("\x1b\\[[IO]")],
  ]).generate();
});

export const drive = pauseAfterEscape(
  weighted([
    [8, prompts],
    [5, commands],
    [4, completions],
    [6, answers],
    [10, navigate],
    [4, chords],
    [6, text],
    [3, paste],
    [4, mouse],
    [4, sizes],
    [1, typed("\x03")],
  ]),
);
