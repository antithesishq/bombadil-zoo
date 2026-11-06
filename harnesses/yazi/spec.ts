// Bombadil specification for yazi, the terminal file manager.
//
// Runs in the Nix sandbox, because yazi's shell prompts execute whatever
// gets typed into them.
import { always, eventually, type Formula } from "@antithesishq/bombadil";
import { extract, weighted } from "@antithesishq/bombadil/terminal";
import {
  CharSets,
  typeFromSet,
} from "@antithesishq/bombadil/terminal/defaults/actions";
import {
  exited,
  keys,
  noCrashText,
  pauseAfterEscape,
  resize,
  startsShowing,
  typePrintableExcept,
} from "../../lib/spec/common.ts";
export {
  exitSuccess,
  noReplacementChars,
} from "@antithesishq/bombadil/terminal/defaults/properties";
export { neverStuckBlank } from "../../lib/spec/common.ts";

// No quit keys, and random typing leaves out q and Q, which both quit: at
// about 100 actions a second they ended most runs within a second or two.

// Properties

// A Rust panic prints "panicked at" before yazi exits.
export const noPanic = noCrashText(/panicked at/);

// yazi is up: its status bar shows the mode from the first frame.
export const startsUp = startsShowing(/\b(NOR|SEL|UNS)\b/);

// The bottom row of the main view holds the status bar, which starts with
// the mode: NOR, SEL (visual select) or UNS (visual unset). Overlays like
// help, tasks and prompts keep it. It only goes away while something takes
// over the terminal, e.g. a blocking shell command or the fzf picker, and
// those return within seconds here. If it stays away while yazi still runs,
// the UI is wedged or drawing garbage.
const statusBar = extract((state) => {
  const rows = state.grid.size.rows;
  return rows > 0 ? state.grid.rowText(rows - 1) : "";
});

export const statusBarReturns: Formula = always(
  eventually(
    () =>
      !!exited.current || /\b(NOR|SEL|UNS)\b/.test(statusBar.current ?? ""),
  ).within(10, "seconds"),
);

// Actions

const navigate = keys(
  "h", "j", "k", "l",
  "\x1b[A", "\x1b[B", "\x1b[C", "\x1b[D",
  "gg", "G", "J", "K", "H", "L", "\x1b[5~", "\x1b[6~", "\x1b[H", "\x1b[F",
  "\x15", "\x04", "\x02", "\x06", // Ctrl+U/D/B/F: half and full page moves
  "gh", "gc", "gd", "g ", "gf", // home, config, downloads, interactive cd, follow
  "\r", "\x1b", "\t",
);

// Selection, clipboard and file operations. They only touch the run's
// scratch copy of the seed tree.
const fileOps = keys(
  " ", "v", "V", "\x01", "\x12", // select, visual, unset visual, all, invert
  "y", "x", "p", "P", "Y", "X", // yank, cut, paste, paste overwrite, unyank
  "-", "_", "\x1f", // symlink, relative symlink, hardlink
  "d", "D", "u", // trash, delete, undo
  "c", "cc", "cC", "cd", "cD", "cf", "cn", // copy path variants
  "o", "O", // open, open interactively (pick an opener)
  "A", // bulk create
  ".", // toggle hidden
);

// Bulk operations: select many entries, then act on them. Renaming several
// files opens the bulk rename editor (EDITOR is true, so it returns at once);
// pasting many creates tasks for the task manager.
const bulkOps = keys(
  "\x01r", " j r", "\x01y", "\x01x", "\x01d", "\x01D",
);

// Keys that open a prompt or picker. Whatever follows is typed into it.
const prompts = keys(
  "a", "r", "/", "?", "n", "N", "f", ":", ";", "s", "S", "z", "Z", "tr",
);

// Editing keys inside a prompt, e.g. Ctrl+K kills to the end of line.
const promptEditing = keys(
  "\x0b", "\x15", "\x17", "\x08", "\x7f", "\x1b[3~", // kills, Backspace, Delete
  "\x1b[H", "\x1b[F", "\x01", "\x05", "\x02", "\x06", // line and char moves
  "\x10", "\x0e", // Ctrl+P, Ctrl+N: recall history
  "\x1bb", "\x1bf", "\x1bd", // Alt+B, Alt+F, Alt+D
);

// A prompt in normal mode (after Esc): vi-style editing, including the
// undo, redo and paste paths that have panicked before.
const promptNormal = keys(
  "i", "I", "a", "A", "v", "V", "r",
  "b", "B", "w", "W", "e", "E", "0", "$", "^",
  "d", "D", "c", "C", "s", "S", "x", "y", "p", "P",
  "u", "U", "\x12", // undo, uppercase, Ctrl+R redo
  "k", "j", // recall history
);

// Tabs, sorting, line modes, help and the preview pane.
const views = keys(
  "t", "tt", "1", "2", "3", "4", "9", "[", "]", "{", "}", "\x1b[Z",
  ",m", ",M", ",b", ",B", ",e", ",E", ",a", ",A", ",n", ",N", ",s", ",S", ",r",
  "mn", "ms", "mm", "mp", "mb", "mo", // line modes
  "~", "\x1bOP", "\x0c", "\x1b[1;2A", "\x1b[1;2B", // help, F1, redraw, seek preview
);

// The task manager, the spot (Tab) and confirm dialogs have their own keys.
const overlays = keys(
  "w", "wj", "wk", "w\r", "wx", // tasks: open, move, inspect, cancel
  "\t", "\tl", "\th", "\tj", "\tcc", // spot: open, swipe, scroll, copy cell
  "y", "n", // answer a confirm dialog
);

export const drive = pauseAfterEscape(
  weighted([
    [30, navigate],
    [18, fileOps],
    [4, bulkOps],
    [10, prompts],
    [10, typePrintableExcept("qQ")],
    [6, promptEditing],
    [6, promptNormal],
    [8, views],
    [5, overlays],
    [3, typeFromSet(CharSets.UNICODE_SAFE)],
    [3, resize([20, 200], [5, 60])],
  ]),
);
