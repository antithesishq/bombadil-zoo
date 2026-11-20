// fx is a coding-agent TUI. The mock provider (mock.py) maps every prompt to
// one of its fixtures by a hash of the text, so generated prompts reach
// replies that stream, fail or arrive malformed, and tool calls that open
// approval and question cards. The properties are fx-independent: it starts,
// never panics or dies on a signal, never leaves a blank screen and exits
// cleanly. Every action is generated: text, prompts, slash commands, pastes,
// keys, clicks and sizes.
import { ActionGenerator } from "@antithesishq/bombadil/actions";
import { type ActionTemplate, extract, weighted } from "@antithesishq/bombadil/terminal";
import { CharSets, typeFromSet } from "@antithesishq/bombadil/terminal/defaults/actions";
import { noCrashText, pauseAfterEscape, resize, startsShowing } from "../../lib/spec/common.ts";
export { exitSuccess } from "@antithesishq/bombadil/terminal/defaults/properties";
export { neverStuckBlank, noFatalSignal } from "../../lib/spec/common.ts";

// default.nix replaces this literal in the saved stress-campaign spec.
const unconstrained = false;

// Properties

export const startsUp = startsShowing(/fx|zoo-mock|ZOO_MOCK_OK|Fixture/);
export const noPanic = noCrashText(
  /thread \d+ panic:|Segmentation fault|unreachable reached|reached unreachable|integer overflow|index out of bounds|fx: (?:invalid transcript transition|command does not fit)/,
);

// Actions

// Types a string generated from a regular expression (Rust syntax).
const typed = (regexp: string): ActionTemplate => ({ TypeText: { Regexp: regexp } });

// Ctrl+U clears the composer first, so the text is not appended to a draft.
const clear = "\x15";

// Prompts and slash commands with generated names and arguments, in ASCII
// or any printable Unicode.
const prompts = weighted([
  [3, typed(`${clear}[ -~]{1,80}\r`)],
  [1, typed(`${clear}\\PC{1,200}\r`)],
]);
const commands = typed(`${clear}/[a-z][a-z-]{0,12}( [ -~]{0,40})?\r`);

// A mode prefix and a few characters, leaving fx's own completion popup open
// for commands, files and skills; the keys below then pick from it.
const completions = typed(`${clear}[/@$][a-z/.]{0,3}`);

// Digits and letters answer cards and pickers.
const answers = typed("[0-9a-z]");

// Arrows, Home/End, PageUp/PageDown, Tab, Shift+Tab, Enter, Space, Escape,
// Backspace and Delete, with and without Shift, Alt and Ctrl.
const navigate = weighted([
  [6, typed("\x1b\\[[ABCDHF]|\x1b\\[[56]~|[\t\r \x1b\x7f]|\x1b\\[Z|\x1b\\[3~")],
  [2, typed("\x1b\\[1;[2-8][ABCDHF]|\x1b\\[[356];[2-8]~")],
]);

// Ctrl and Alt chords. Ctrl+C, Ctrl+D, Ctrl+Q and Ctrl+Z quit or suspend,
// so they are left out.
const chords = typed("[\x01\x02\x05-\x10\x12-\x19\x1f]|\x1b[a-z\x7f]");

// Bracketed pastes of any text, including newlines and control characters.
const paste = typed("\x1b\\[200~(?s:.){0,3000}\x1b\\[201~");

const text = weighted([
  [5, typeFromSet(CharSets.ASCII_PRINTABLE)],
  [2, typeFromSet(CharSets.UNICODE_SAFE)],
]);

const sizes = unconstrained
  ? weighted([[4, resize([1, 500], [1, 150])], [1, resize([1, 4], [1, 4])]])
  : resize([40, 250], [12, 70]);

// Clicks and wheel land inside the window as it currently is; focus leaves
// and returns.
const size = extract((state) => state.grid.size);
const mouse = new ActionGenerator<ActionTemplate>(() => {
  const { columns, rows } = size.current ?? { columns: 100, rows: 40 };
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
    [4, commands],
    [4, completions],
    [6, answers],
    [10, navigate],
    [3, chords],
    [6, text],
    [3, paste],
    [4, mouse],
    [4, sizes],
  ]),
);
