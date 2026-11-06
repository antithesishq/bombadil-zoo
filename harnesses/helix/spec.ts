// Bombadil specification for Helix.
//
// Helix exits with a nonzero code on purpose (`:cq`), so this spec checks
// for panics and fatal signals instead of exitSuccess.
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
  screen,
  startsShowing,
} from "../../lib/spec/common.ts";
export { noReplacementChars } from "@antithesishq/bombadil/terminal/defaults/properties";
export { neverStuckBlank, noFatalSignal } from "../../lib/spec/common.ts";

// Properties

// A Rust panic prints "panicked at" before Helix exits.
export const noPanic = noCrashText(/panicked at/);

// The first file, src/main.c, is on screen.
export const startsUp = startsShowing(/#include <stdio\.h>/);

// The status line shows the mode: NOR, INS or SEL. Pickers and popups draw
// over the buffer but leave it in place, and :sh output and prompts return
// within seconds. If it stays away for 5s while Helix runs, the UI is
// wedged. The bound has to fit well inside a run (10s by default), or the
// property can never fail. In a narrow terminal the status line drops the
// mode, so below 60 columns this holds trivially.
const width = extract((state) => state.grid.size.columns);

export const statusLineReturns: Formula = always(
  eventually(
    () =>
      !!exited.current ||
      (width.current ?? 0) < 60 ||
      /\b(NOR|INS|SEL)\b/.test(screen.current ?? ""),
  ).within(5, "seconds"),
);

// Actions

const motions = keys(
  "h", "j", "k", "l", "w", "b", "e", "W", "B", "E", "f(", "t;", "F#", "T)",
  "gg", "ge", "gh", "gl", "gs", "gt", "gc", "gb", "gn", "gp", "g.", "%",
  "\x04", "\x15", "\x06", "\x02", // Ctrl+D/U/F/B
  "\x0f", "\x09", // Ctrl+O, Ctrl+I: jumplist
  "n", "N", "*", "\x1b*",
);

// Tree-sitter motions and text objects: functions, types, arguments,
// comments, tests, paragraphs and changes.
const syntax = keys(
  "]f", "[f", "]t", "[t", "]a", "[a", "]c", "[c", "]T", "[T", "]p", "[p",
  "]d", "[d", "]g", "[g", "]D", "[D",
  "mif", "maf", "mit", "mat", "mia", "maa", "mic", "mac", "miT", "maT",
  "mip", "map", "miw", "maW", "mi(", "ma{", "mi\"", "mm",
  "\x1bo", "\x1bi", "\x1bp", "\x1bn", "\x1bI", "\x1bu", // expand, shrink, siblings
);

// Selections are central to Helix: extend, split, keep, rotate, align.
const selections = keys(
  "x", "X", "v", ";", "\x1b;", ",", "\x1b,", "C", "\x1bC", "s", "S", "\x1bs",
  "K", "\x1bK", "&", "_", "\x1b-", "\x1b_", "%", "(", ")", "\x1b(", "\x1b)",
  "\x1bx", "\x1b:", // shrink to line bounds, ensure forward direction
);

// Surround: add, delete and replace pairs.
const surround = keys(
  "ms(", "ms\"", "ms[", "msq", "md(", "md\"", "mdq", "mr([", "mr\"'", "mr({",
);

// Jump labels: gw shows two-letter labels; typing one jumps there.
const jumpLabels = keys("gw", "gwaa", "gwab", "gwba", "gwzz");

const edits = keys(
  "d", "\x1bd", "c", "\x1bc", "y", "p", "P", "R", "u", "U", "\x1bu", "\x1bU",
  ".", "~", "`", "\x1b`", ">", "<", "=", "J", "\x1bJ", "r!", "\x01", "\x18",
  "\x1b;", "gq",
);

// Registers: named, black hole, search, selection indices, clipboard. The
// sandbox has no clipboard provider, so those take the error path.
const registers = keys(
  "\"ay", "\"ap", "\"Ay", "\"_d", "\"/p", "\"#p", "\".p", "\"%p",
  "\"+y", "\"+p", "\"*y", " y", " p", " P", " R",
);

// Macros: record with Q into the default register, replay with q.
const macros = keys("Q", "q", "Qwd", "Qjx", "\"aQ", "\"aq", "3q");

const insert = keys(
  "i", "a", "I", "A", "o", "O",
  "\x0e", "\x10", "\x12\"", "\x12a", "\x17", "\x15", "\x0b", // completion, registers, kills
);

// Pickers with input, so they filter, preview and open something.
const pickers = keys(
  " f", " F", " b", " j", " s", " /", " ?", " '", " g", " d", " D",
  " fsrc\r", " fmain\r", " b\r", " /fib\r", " /text\r", " ?sort\r",
  " ?reflow\r", " ?split\r",
);

const windows = keys(
  "\x17s", "\x17v", "\x17w", "\x17q", "\x17o", "\x17h", "\x17l", "\x17j",
  "\x17k", "\x17H", "\x17L", "\x17n", "zz", "zt", "zb", "zj", "zk", "Z",
);

// Typed commands, including ones that touch other files and the shell.
const commands = keys(
  ...[
    "sort", "rsort", "reflow", "reflow 20", "w", "w new.txt", "o data.json",
    "o long-lines.txt", "o blob.bin", "o crlf.txt", "o whitespace.txt",
    "o empty.txt", "new", "buffer-close", "buffer-next", "buffer-previous",
    "vsplit", "hsplit", "set-language json", "set-language python",
    "set soft-wrap.enable true", "toggle soft-wrap.enable", "sh echo hi",
    "pipe sort", "pipe-to cat", "insert-output echo hi",
    "append-output printf 'a\\nb'", "run-shell-command echo hi", "reload",
    "reload-all", "tree-sitter-scopes", "tree-sitter-subtree", "log-open",
    "goto 50000", "goto 1", "earlier 5", "later 5", "earlier 1m",
    "theme base16_default", "line-ending crlf", "line-ending lf",
    "encoding latin1", "encoding utf-8", "indent-style 2", "indent-style tabs",
    "character-info", "yank-join", "clipboard-yank", "config-reload",
    "lsp-restart", "update",
  ].map((c) => `:${c}\r`),
  ":", "/", "?", "|", "!", "\x1b|", "\x1b!",
);

export const drive = pauseAfterEscape(
  weighted([
    [20, motions],
    [8, syntax],
    [10, selections],
    [3, surround],
    [2, jumpLabels],
    [10, edits],
    [4, registers],
    [3, macros],
    [6, insert],
    [5, pickers],
    [4, windows],
    [7, commands],
    [10, typeFromSet(CharSets.ASCII_PRINTABLE)],
    [3, typeFromSet(CharSets.UNICODE_SAFE)],
    [10, keys("\x1b")],
    [2, resize([20, 200], [5, 60])],
  ]),
);
