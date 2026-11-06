// Building blocks shared by the harness specs. A spec re-exports the
// properties it wants and builds its actions from these helpers.
import { always, eventually, type Formula } from "@antithesishq/bombadil";
import { ActionGenerator, CharSet, leaf } from "@antithesishq/bombadil/actions";
import { type ActionTemplate, extract } from "@antithesishq/bombadil/terminal";
import {
  lastAction,
  typeFromSet,
} from "@antithesishq/bombadil/terminal/defaults/actions";

// The visible screen as text, one line per row.
export const screen = extract((state) => {
  const rows = [];
  for (let i = 0; i < state.grid.size.rows; i++) {
    rows.push(state.grid.rowText(i));
  }
  return rows.join("\n");
});

const size = extract((state) => state.grid.size);

export const exited = extract((state) => state.exitStatus !== null);

// Fails once the screen shows text matching `crash`. Harnesses copy the
// target's stderr to the terminal, so a panic message shows up here.
export function noCrashText(crash: RegExp): Formula {
  return always(() => !crash.test(screen.current ?? ""));
}

// The target starts and shows `text` within 5 seconds, or exits by then,
// e.g. because the fuzzer quit it. Without this, a target that fails to
// start can look like a clean campaign. Match something in the target's
// first frame: early input can move away before data that loads later
// appears. The bound has to be well under bombadil's run length (10s by
// default), because a run that ends before the deadline leaves the property
// undecided, and an undecided property isn't reported.
export function startsShowing(text: RegExp): Formula {
  return eventually(
    () => !!exited.current || text.test(screen.current ?? ""),
  ).within(5, "seconds");
}

const exitSignal = extract((state) => state.exitStatus?.signal ?? null);

// The target never dies from a signal, e.g. SIGSEGV or SIGABRT. Useful for
// targets that exit with a nonzero code on purpose, where exitSuccess would
// flag ordinary use, and for C programs, which print no panic message.
export const noFatalSignal: Formula = always(() => exitSignal.current == null);

// The screen may blank during a redraw, but never stays blank while the
// target runs. Quitting is fine; the screen is empty after that.
export const neverStuckBlank: Formula = always(
  eventually(
    () => !!exited.current || (screen.current ?? "").trim() !== "",
  ).within(5, "seconds"),
);

// Types one of the literals per step.
export function keys(...literals: string[]): ActionGenerator<ActionTemplate> {
  return typeFromSet(CharSet.fromLiterals(...literals));
}

// Types one printable ASCII character per step, except the given ones. At
// about 100 actions a second, random typing that includes a target's quit
// key ends most runs within a second or two.
export function typePrintableExcept(
  excluded: string,
): ActionGenerator<ActionTemplate> {
  const literals: string[] = [];
  for (let code = 0x20; code <= 0x7e; code++) {
    const char = String.fromCharCode(code);
    if (!excluded.includes(char)) literals.push(char);
  }
  return keys(...literals);
}

export function resize(
  columns: [number, number],
  rows: [number, number],
): ActionTemplate {
  return { Resize: { columns, rows } };
}

// Terminals can't tell a lone Esc from the start of Alt+key when the next
// byte arrives right behind it, so "Esc, y" reads as Alt+y. After any action
// that ends in Esc, this sends a same-size resize first, which writes no
// bytes and gives the target a step to see the Esc on its own.
export function pauseAfterEscape(
  actions: ActionGenerator<ActionTemplate>,
): ActionGenerator<ActionTemplate> {
  return new ActionGenerator(() => {
    const last = lastAction.current;
    const current = size.current;
    if (
      current &&
      last &&
      "TypeText" in last &&
      last.TypeText.endsWith("\x1b")
    ) {
      return leaf<ActionTemplate>({
        Resize: { columns: current.columns, rows: current.rows },
      });
    }
    return actions.generate();
  });
}
