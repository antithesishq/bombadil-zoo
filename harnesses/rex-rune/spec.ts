import { always } from "@antithesishq/bombadil";
import {
  type ActionTemplate,
  actions,
  extract,
  float,
  string,
  weighted,
} from "@antithesishq/bombadil/external";

type Rect = [number, number, number, number];
type Element = {
  key: string | null;
  path: string;
  role: string;
  label: string | null;
  text: string | null;
  rect: Rect;
  visible: Rect;
  opacity: number;
  focused: boolean;
  focusable: boolean;
  inert: boolean;
  exiting: boolean;
  moving: boolean;
};
type State = { elements: Element[]; viewport: [number, number] };
const ui = extract((state: State) => state);
const sections = [
  "interface",
  "terminal",
  "notifications",
  "integrations",
  "hosts",
  "shortcuts",
  "updates",
  "about",
];
const PANE_PRESSURE_LIMIT = 48;

function validRect(rect: Rect): boolean {
  return rect.every(Number.isFinite) && rect[2] >= 0 && rect[3] >= 0;
}

function contains(outer: Rect, inner: Rect, epsilon = 0.05): boolean {
  // Rune reports f32 geometry; allow rounding at clip boundaries.
  return (
    inner[0] >= outer[0] - epsilon &&
    inner[1] >= outer[1] - epsilon &&
    inner[0] + inner[2] <= outer[0] + outer[2] + epsilon &&
    inner[1] + inner[3] <= outer[1] + outer[3] + epsilon
  );
}

function live(element: Element): boolean {
  return !element.exiting;
}

// Keys such as "segment0" are local to their parent and need not be unique.
// Click the clipped visible area instead of blindly tapping those keys.
function point(element: Element): { x: number; y: number } | null {
  if (element.inert || element.exiting || element.opacity <= 0) return null;
  const [x, y, width, height] = element.visible;
  const left = Math.max(0, x);
  const top = Math.max(0, y);
  const right = Math.min(ui.current.viewport[0], x + width);
  const bottom = Math.min(ui.current.viewport[1], y + height);
  return right > left && bottom > top
    ? { x: (left + right) / 2, y: (top + bottom) / 2 }
    : null;
}

export const workspacePresent = always(() =>
  ui.current.elements.some(
    (element) => live(element) && element.key === "toolbar",
  ),
);
export const validGeometry = always(() =>
  ui.current.elements.every(
    (element) => validRect(element.rect) && validRect(element.visible),
  ),
);
export const validViewport = always(() =>
  ui.current.viewport.every((size) => Number.isFinite(size) && size > 0),
);
export const validOpacity = always(() =>
  ui.current.elements.every(
    (element) =>
      Number.isFinite(element.opacity) &&
      element.opacity >= 0 &&
      element.opacity <= 1,
  ),
);
export const clippingWithinLayout = always(() =>
  ui.current.elements.every(
    (element) =>
      element.visible[2] === 0 ||
      element.visible[3] === 0 ||
      contains(element.rect, element.visible),
  ),
);
export const uniqueLivePaths = always(() => {
  const paths = ui.current.elements.filter(live).map((element) => element.path);
  return new Set(paths).size === paths.length;
});
export const singleFocus = always(
  () => ui.current.elements.filter((element) => element.focused).length <= 1,
);
export const focusIsInteractive = always(() =>
  ui.current.elements.every(
    (element) =>
      !element.focused ||
      (element.focusable && !element.inert && !element.exiting),
  ),
);
export const exitingIsInert = always(() =>
  ui.current.elements.every((element) => !element.exiting || element.inert),
);
export const dialogsFitViewport = always(() =>
  ui.current.elements.every(
    (element) =>
      element.role !== "dialog" ||
      element.exiting ||
      element.moving ||
      contains([0, 0, ...ui.current.viewport], element.rect),
  ),
);
export const settingsStructure = always(() => {
  const elements = ui.current.elements.filter(live);
  if (!elements.some((element) => element.key === "close-settings"))
    return true;
  return (
    // Value pickers change the panel title while Settings stays inert below them.
    elements.some((element) => element.role === "dialog") &&
    sections.every((section) =>
      elements.some(
        (element) =>
          element.key === `settings-section:${section}` &&
          element.role === "tab",
      ),
    ) &&
    elements.filter((element) => element.key?.startsWith("settings-scroll:"))
      .length === 1
  );
});

function inPane(element: Element, block: string): boolean {
  return ui.current.elements.some(
    (pane) =>
      live(pane) &&
      pane.key === `pane:${block}` &&
      element.path.startsWith(`${pane.path}/`),
  );
}

export const terminalGridsHavePanes = always(() =>
  ui.current.elements.every(
    (element) =>
      !live(element) ||
      !element.key?.startsWith("grid:") ||
      inPane(element, element.key.slice(5)),
  ),
);
export const paneControlsHavePanes = always(() =>
  ui.current.elements.every((element) => {
    const key = element.key ?? "";
    return (
      !live(element) ||
      !/^pane-(header|actions|split-right|split-down|zoom|close|zoomed):/.test(
        key,
      ) ||
      inPane(element, key.slice(key.indexOf(":") + 1))
    );
  }),
);
export const terminalSearchStructure = always(() =>
  ui.current.elements.every((element) => {
    if (!live(element) || !element.key?.startsWith("search:")) return true;
    const block = element.key.slice(7);
    return (
      inPane(element, block) &&
      ["search-field", "find-next", "find-previous", "find-close"].every(
        (prefix) =>
          ui.current.elements.some(
            (control) =>
              live(control) &&
              control.key === `${prefix}:${block}` &&
              control.path.startsWith(`${element.path}/`),
          ),
      )
    );
  }),
);
export const searchControlsHaveSearch = always(() => {
  const elements = ui.current.elements.filter(live);
  const searches = elements.filter((element) =>
    element.key?.startsWith("search:"),
  );
  return elements.every(
    (element) =>
      !/^(search-field|find-(next|previous|close|count)):/.test(
        element.key ?? "",
      ) ||
      searches.some((search) => element.path.startsWith(`${search.path}/`)),
  );
});
export const uniqueLiveTerminalKeys = always(() => {
  const keys: string[] = [];
  for (const element of ui.current.elements) {
    if (
      live(element) &&
      element.key !== null &&
      /^(grid|search):/.test(element.key)
    ) {
      keys.push(element.key);
    }
  }
  return new Set(keys).size === keys.length;
});

export const singleActiveDialog = always(
  () =>
    ui.current.elements.filter(
      (element) => live(element) && element.role === "dialog" && !element.inert,
    ).length <= 1,
);
export const popupMakesDialogsInert = always(() => {
  const elements = ui.current.elements.filter(live);
  return (
    !elements.some(
      (element) => element.key === "menu-surface" && !element.inert,
    ) ||
    elements
      .filter((element) => element.role === "dialog")
      .every((dialog) => dialog.inert)
  );
});
export const stationaryPopupsFitViewport = always(() =>
  ui.current.elements.every(
    (element) =>
      !live(element) ||
      element.key !== "menu-surface" ||
      element.moving ||
      contains([0, 0, ...ui.current.viewport], element.rect, 0.75),
  ),
);
export const stationaryGridContentsWithinGrids = always(() => {
  const elements = ui.current.elements.filter(live);
  const grids = elements.filter((element) => element.key?.startsWith("grid:"));
  if (grids.some((grid) => grid.moving)) return true;
  return elements.every((element) => {
    if (element.moving || element.visible[2] === 0 || element.visible[3] === 0)
      return true;
    const owners = grids.filter((grid) =>
      element.path.startsWith(`${grid.path}/`),
    );
    return (
      owners.length === 0 ||
      owners.some((grid) => contains(grid.visible, element.visible, 0.75))
    );
  });
});

export const stationaryTerminalContentWithinPanes = always(() => {
  const elements = ui.current.elements.filter(live);
  const panes = elements.filter((element) => element.key?.startsWith("pane:"));
  // Springs may briefly separate a card from the content it is animating.
  if (panes.some((pane) => pane.moving)) return true;
  return elements.every((element) => {
    if (
      !/^(grid|search):/.test(element.key ?? "") ||
      element.moving ||
      element.visible[2] === 0 ||
      element.visible[3] === 0
    )
      return true;
    return panes.some(
      (pane) =>
        element.path.startsWith(`${pane.path}/`) &&
        // Rounded card clips extend half a point past the card's layout rect.
        contains(pane.visible, element.visible, 0.75),
    );
  });
});

export const stationaryPanesDoNotOverlap = always(() => {
  const panes = ui.current.elements.filter(
    (element) => live(element) && element.key?.startsWith("pane:"),
  );
  // Springing cards may cross while their layout changes.
  if (panes.some((pane) => pane.moving)) return true;
  return panes.every((pane, index) =>
    panes.slice(index + 1).every((other) => {
      const [x, y, w, h] = pane.visible;
      const [ox, oy, ow, oh] = other.visible;
      return (
        Math.min(x + w, ox + ow) - Math.max(x, ox) <= 0.05 ||
        Math.min(y + h, oy + oh) - Math.max(y, oy) <= 0.05
      );
    }),
  );
});

export const uniqueLivePaneKeys = always(() => {
  const keys = ui.current.elements
    .filter((element) => live(element) && element.key?.startsWith("pane:"))
    .map((element) => element.key);
  return new Set(keys).size === keys.length;
});
export const emptyViewHasNoPanes = always(() => {
  const elements = ui.current.elements.filter(live);
  return (
    !elements.some((element) => element.key === "empty") ||
    !elements.some((element) => element.key?.startsWith("pane:"))
  );
});
export const dividersRequireSplitPanes = always(() => {
  const elements = ui.current.elements.filter(live);
  return (
    !elements.some((element) => element.key?.startsWith("divider:")) ||
    elements.filter((element) => element.key?.startsWith("pane:")).length > 1
  );
});
export const closeConfirmationStructure = always(() => {
  const elements = ui.current.elements.filter(live);
  return elements
    .filter((element) => element.key === "confirm-close")
    .every((confirm) =>
      elements.some(
        (dialog) =>
          dialog.role === "dialog" &&
          confirm.path.startsWith(`${dialog.path}/`) &&
          elements.some(
            (cancel) =>
              cancel.key === "cancel-close" &&
              cancel.path.startsWith(`${dialog.path}/`),
          ),
      ),
    );
});

export const dialogOwnsFocus = always(() => {
  const elements = ui.current.elements.filter(live);
  const dialog = elements.find(
    (element) => element.role === "dialog" && !element.inert,
  );
  return (
    !dialog ||
    elements.every(
      (element) =>
        !element.focused ||
        element.path === dialog.path ||
        element.path.startsWith(`${dialog.path}/`),
    )
  );
});
export const pickerMakesSettingsInert = always(() => {
  const elements = ui.current.elements.filter(live);
  if (
    !elements.some((element) => element.key === "menu-surface") ||
    !elements.some((element) => element.key === "close-settings")
  )
    return true;
  return elements
    .filter((element) => element.role === "dialog")
    .every((dialog) =>
      elements
        .filter(
          (element) =>
            element.path === dialog.path ||
            element.path.startsWith(`${dialog.path}/`),
        )
        .every((element) => element.inert && !element.focused),
    );
});
export const zoomHidesOtherPanes = always(() => {
  const elements = ui.current.elements.filter(live);
  const panes = elements.filter((element) => element.key?.startsWith("pane:"));
  return elements
    .filter((element) => element.key?.startsWith("pane-zoomed:"))
    .every(
      (chip) =>
        panes.length === 1 &&
        panes[0].key === `pane:${chip.key?.slice("pane-zoomed:".length)}`,
    );
});
export const searchCountWithinRange = always(() =>
  ui.current.elements.every((element) => {
    if (!live(element) || !element.key?.startsWith("find-count:")) return true;
    if (element.text === "No matches") return true;
    const count = /^(\d+)\/(\d+)$/.exec(element.text ?? "");
    // A search may have matches before its worker selects the first one (0/N).
    return (
      count !== null &&
      Number(count[2]) > 0 &&
      Number(count[1]) <= Number(count[2])
    );
  }),
);

const controls = actions(() => {
  const keyCounts = new Map<string, number>();
  for (const element of ui.current.elements.filter(live)) {
    if (element.key) {
      keyCounts.set(element.key, (keyCounts.get(element.key) ?? 0) + 1);
    }
  }
  return ui.current.elements.flatMap((element): ActionTemplate[] => {
    // Closing the native window is outside this persistent-runtime example.
    if (
      element.key === "close-app" ||
      (!element.focusable &&
        ![
          "button",
          "checkbox",
          "switch",
          "tab",
          "textbox",
          "combobox",
          "radio",
          "option",
          "menuitem",
          "menuitemcheckbox",
          "menuitemradio",
          "slider",
          "spinbutton",
          "link",
        ].includes(element.role))
    )
      return [];
    const at = point(element);
    if (!at) return [];
    return [
      { Click: at },
      ...(element.key && keyCounts.get(element.key) === 1
        ? [{ Tap: { key: element.key } }]
        : []),
    ];
  });
});

// Keep navigation and escape competitive even on pages with many controls.
const navigation = actions(() =>
  ui.current.elements.flatMap((element) =>
    element.key?.startsWith("settings-section:") && point(element)
      ? [{ Tap: { key: element.key } }]
      : [],
  ),
);
const recovery = actions(() => [
  { Key: { name: "Escape" } },
  ...ui.current.elements.flatMap((element) =>
    ["settings", "close-settings", "popup-dismiss", "scrim"].includes(
      element.key ?? "",
    ) &&
    point(element) &&
    element.key
      ? [{ Tap: { key: element.key } }]
      : [],
  ),
]);

// Give lifecycle controls a separate budget instead of diluting them among
// terminal cells, Settings controls and the command palette's many rows.
const connectedControls = actions(() =>
  ui.current.elements.flatMap((element) =>
    element.key &&
    /^(commands$|identity$|toggle-sidebar$|new-tab$|empty-action$|host-new-session:|new-session-on:|session:|sidebar-tab:|tab:|pane-split-|pane-zoom:|pane-close:|grid:|find-(next|previous|close):)/.test(
      element.key,
    ) &&
    point(element)
      ? [{ Tap: { key: element.key } }]
      : [],
  ),
);

// Reach the destructive confirmation, not just its default "Keep running".
// Both confirming and cancelling remain available; all programs are sandboxed.
const splitDestruction = actions(() => {
  const elements = ui.current.elements.filter(live);
  if (
    elements.some(
      (element) =>
        element.key === "confirm-close" &&
        element.label === "Close and end programs" &&
        point(element),
    )
  ) {
    return weighted([
      [8, { Tap: { key: "confirm-close" } }],
      [1, { Tap: { key: "cancel-close" } }],
      [1, { Key: { name: "Escape" } }],
    ]).generate();
  }
  if (
    elements.some(
      (element) => element.role === "dialog" || element.key === "menu-surface",
    )
  )
    return [];
  return elements.flatMap((element) =>
    element.key?.startsWith("pane-close:") && point(element)
      ? [{ Tap: { key: element.key } }]
      : [],
  );
});

// Split one victim repeatedly instead of distributing splits across an easy,
// shallow layout. At narrow widths the header loses its split buttons, so keep
// opening Commands as a fallback. Other generators supply the actual command.
const deepSplitPressure = actions(() => {
  const elements = ui.current.elements.filter(live);
  if (
    elements.some(
      (element) =>
        element.key === "close-settings" ||
        element.key === "menu-surface" ||
        element.role === "dialog",
    )
  )
    return [];
  const panes = elements.filter(
    (element) => element.key?.startsWith("pane:") && point(element),
  );
  if (panes.length === 0 || panes.length >= PANE_PRESSURE_LIMIT) return [];
  const victim = panes.reduce((smallest, pane) =>
    pane.rect[2] * pane.rect[3] < smallest.rect[2] * smallest.rect[3]
      ? pane
      : smallest,
  );
  const block = victim.key?.slice("pane:".length);
  if (!block) return [];
  const splits = ["right", "down", "left", "up"].flatMap(
    (direction): ActionTemplate[] => {
      const key = `pane-split-${direction}:${block}`;
      return elements.some((element) => element.key === key && point(element))
        ? [{ Tap: { key } }, { Tap: { key } }]
        : [];
    },
  );
  const commands = elements.find(
    (element) => element.key === "commands" && point(element),
  );
  return [...splits, ...(commands ? [{ Tap: { key: "commands" } }] : [])];
});

// Keep mutating a crowded layout, including panes with an open search. Grid
// taps move focus back to the terminal without first dismissing its search bar.
const hostileLifecycle = actions(() => {
  const elements = ui.current.elements.filter(live);
  if (
    elements.some(
      (element) =>
        element.key === "close-settings" ||
        element.key === "menu-surface" ||
        element.role === "dialog",
    )
  )
    return [];
  if (!elements.some((element) => element.key?.startsWith("pane:"))) return [];
  const pointerActions = elements.flatMap((element): ActionTemplate[] => {
    const key = element.key ?? "";
    if (!point(element)) return [];
    if (key.startsWith("grid:")) return [{ Tap: { key } }];
    if (/^pane-(zoom|close):/.test(key))
      return [{ Tap: { key } }, { Tap: { key } }];
    if (/^find-(next|previous):/.test(key))
      return [{ Tap: { key } }, { Tap: { key } }, { Tap: { key } }];
    return [];
  });
  return [
    ...pointerActions,
    ...["Tab", "Enter", "PageUp", "PageDown", "Home", "End"].map((name) => ({
      Key: { name },
    })),
  ];
});

// Switch, reorder and recreate workspaces while their old panes still have
// active rendering, input or search work.
const workspaceChurn = actions(() => {
  const elements = ui.current.elements.filter(live);
  const crowded =
    elements.filter((pane) => pane.key?.startsWith("pane:")).length >= 4;
  const searching = elements.some((element) =>
    element.key?.startsWith("search:"),
  );
  if (
    elements.some(
      (element) =>
        element.key === "close-settings" ||
        element.key === "menu-surface" ||
        element.role === "dialog",
    ) ||
    (!crowded && !searching)
  )
    return [];
  return elements.flatMap((element): ActionTemplate[] => {
    const key = element.key ?? "";
    return /^(new-tab$|host-new-session:|new-session-on:|session:|sidebar-tab:|tab:|identity$|toggle-sidebar$)/.test(
      key,
    ) && point(element)
      ? [{ Tap: { key } }, { Tap: { key } }]
      : [];
  });
});

// Exercise focus and activation while dialogs, pickers and confirmations are
// transitioning. Coordinates deliberately include repeated local option keys.
const overlayPressure = actions(() => {
  const elements = ui.current.elements.filter(live);
  if (
    !elements.some(
      (element) => element.role === "dialog" || element.key === "menu-surface",
    )
  )
    return [];
  const controls = elements.flatMap((element): ActionTemplate[] => {
    const at = point(element);
    if (!at) return [];
    if (element.key === "confirm-close")
      return [{ Click: at }, { Click: at }, { Click: at }, { Click: at }];
    if (
      ["cancel-close", "close-settings", "popup-dismiss", "scrim"].includes(
        element.key ?? "",
      ) ||
      element.role === "option"
    )
      return [{ Click: at }];
    return [];
  });
  return [
    ...controls,
    ...["Tab", "Tab", "Enter", "Enter", "Escape"].map((name) => ({
      Key: { name },
    })),
  ];
});

// Submit hostile field contents repeatedly while validation and model updates
// may still be pending. Terminal search and Commands have their own generators.
const formSubmission = actions(() => [
  ...[
    "\n",
    "\n\n",
    " \n\n",
    "zoo\n\n",
    `${"🦙éא".repeat(256)}\n\n`,
    "\u0000\r\u001b\n\n",
    "unix:///nonexistent-zoo-rex.sock\n\n",
    "https://127.0.0.1:1\n\n",
  ].map((text) => ({ TypeText: { text } })),
  { Key: { name: "Enter" } },
  { Key: { name: "Enter" } },
]).when(() =>
  ui.current.elements.some(
    (element) =>
      live(element) &&
      element.focused &&
      !element.inert &&
      element.role === "textbox" &&
      element.label !== "Search commands, sessions, and tabs…" &&
      !element.key?.startsWith("search-field:"),
  ),
);

function emptyCommandSearch(): boolean {
  return ui.current.elements.some(
    (element) =>
      live(element) &&
      element.focused &&
      !element.inert &&
      element.label === "Search commands, sessions, and tabs…" &&
      element.text === "",
  );
}

const commandSearch = actions(() =>
  [
    "New session",
    "New tab",
    "Rename session",
    "Rename tab",
    "Rename pane",
    "Next session",
    "Previous session",
    "Next tab",
    "Previous tab",
    "Move tab left",
    "Move tab right",
    "Move tab up",
    "Move tab down",
    "Mute tab",
    "Unmute tab",
    "Close other tabs",
    "Back in history",
    "Forward in history",
    "Split right",
    "Split down",
    "Split left",
    "Split up",
    "Split best fit",
    "Zoom pane",
    "Restore pane",
    "Focus next pane",
    "Focus previous pane",
    "Focus pane left",
    "Focus pane right",
    "Focus pane up",
    "Focus pane down",
    "Reveal pane headers",
    "Hide pane headers",
    "Show sidebar",
    "Hide sidebar",
    "Show tabs in sidebar",
    "Show tabs in toolbar",
    "Use compact panes",
    "Use comfortable panes",
    "Increase terminal font size",
    "Decrease terminal font size",
    "Reset terminal font size",
    "Increase interface zoom",
    "Decrease interface zoom",
    "Reset interface zoom",
    "Change terminal theme",
    "Change interface theme",
    "Search terminal",
    "Find next",
    "Find previous",
    "Clear terminal",
    "Reset terminal",
    "Reconnect terminal",
    "Refresh sessions",
    "Close pane",
    "Close pane or tab",
    "Close tab",
    "Close session",
  ].map((text) => ({ TypeText: { text: `${text}\n` } })),
).when(emptyCommandSearch);

// Once Commands opens in a difficult state, keep the pressure on that state
// instead of spending most queries on navigation and dismissal.
const hostileCommandSearch = actions(() => {
  const paneCount = ui.current.elements.filter(
    (element) => live(element) && element.key?.startsWith("pane:"),
  ).length;
  return [
    ...(paneCount < PANE_PRESSURE_LIMIT
      ? [
          "Split right",
          "Split down",
          "Split left",
          "Split up",
          "Split best fit",
        ]
      : []),
    "Zoom pane",
    "Restore pane",
    "Focus next pane",
    "Focus previous pane",
    "Search terminal",
    "Find next",
    "Find previous",
    "Clear terminal",
    "Reset terminal",
    "Reconnect terminal",
    "Increase terminal font size",
    "Decrease terminal font size",
    "Reset terminal font size",
    "Increase interface zoom",
    "Decrease interface zoom",
    "Reset interface zoom",
    "Change terminal theme",
    "Change interface theme",
    "Show tabs in sidebar",
    "Show tabs in toolbar",
    "Use compact panes",
    "Use comfortable panes",
    "Reveal pane headers",
    "Hide pane headers",
    "Show sidebar",
    "Hide sidebar",
    "Close pane",
    "Close pane or tab",
    "Close tab",
    "Close session",
  ].map((text) => ({ TypeText: { text: `${text}\n` } }));
}).when(
  () =>
    emptyCommandSearch() &&
    ui.current.elements.some(
      (element) => live(element) && element.key?.startsWith("pane:"),
    ),
);

const workspaceCommandSearch = actions(() =>
  [
    "New session",
    "New tab",
    "Next session",
    "Previous session",
    "Next tab",
    "Previous tab",
    "Move tab left",
    "Move tab right",
    "Move tab up",
    "Move tab down",
    "Mute tab",
    "Unmute tab",
    "Close other tabs",
    "Back in history",
    "Forward in history",
    "Refresh sessions",
    "Reconnect host",
    "Close tab",
    "Close session",
  ].map((text) => ({ TypeText: { text: `${text}\n` } })),
).when(() => {
  if (!emptyCommandSearch()) return false;
  const elements = ui.current.elements.filter(live);
  return (
    elements.some((element) => element.key?.startsWith("search:")) ||
    elements.filter((element) => element.key?.startsWith("pane:")).length >= 4
  );
});

const terminalInput = actions(() =>
  [
    "printf 'zoo terminal input\\n'\n",
    "printf 'blåbær 🦙 中文 é אבג\\n'\n",
    "printf '\\033[31mred\\033[0m plain\\n'\n",
    "printf '\\033[2J\\033[Hcleared\\n'\n",
    "printf '\\033]0;Zoo title\\007title changed\\n'\n",
    "printf '\\033]8;;https://example.invalid/\\007link\\033]8;;\\007\\n'\n",
    "i=0; while [ $i -lt 120 ]; do printf 'zoo row %03d\\n' $i; i=$((i+1)); done\n",
    "(i=0; while [ $i -lt 1200 ]; do printf 'burst %04d 🦙 é אבג \\033[31mred\\033[0m\\n' $i; i=$((i+1)); done) &\n",
    "printf '%0320d\\n' 1\n",
    "printf '%016384d\\n' 1\n",
    "printf '%065536d\\n' 1\n",
    "printf '👩🏽‍💻éאבג %.0s' {1..512}\n",
    "printf '\\033[?1049h\\033[2J\\033[Halternate\\n'; sleep 0.05; printf '\\033[?1049lrestored\\n'\n",
    "printf '\\033[9999;9999Hedge\\033[1;1Hhome\\n'\n",
    "printf '\\033[2;8r\\033[2;1Htop\\033[8;1Hbottom\\033[r\\n'\n",
    "printf '\\033[3;4;9;53mitalic underline strike overline\\033[0m\\n'\n",
    "printf '\\033[38;2;255;0;128mtruecolor\\033[48;5;22m background\\033[0m\\n'\n",
    "printf '\\033[?1000;1002;1006;2004hmouse enabled\\n'\n",
    "printf '\\033[?1000;1002;1006;2004lmouse disabled\\n'\n",
    "printf '\\033]52;c;em9vLWNsaXBib2FyZA==\\007clipboard\\n'\n",
    "printf '\\033_Ga=T,f=24,s=1,v=1;AAAA\\033\\\\image\\n'\n",
    "printf '\\033]8;;https://example.invalid/\\007🦙 link\\033]8;;\\007\\n'\n",
    "printf '\\033]0;%s\\007done\\n' \"$(printf '%0512d' 0)\"\n",
    "printf '\\033[31m%s\\033[0m\\n' \"$(printf '%08192d' 1)\"\n",
    "pwd\n",
    "exit\n",
    "printf 'partial input'",
    "\n",
  ].map((text) => ({ TypeText: { text } })),
).when(() => {
  const elements = ui.current.elements.filter(live);
  // Terminal keys are handled at app level: grids do not hold Rune text focus.
  // An unfocused search bar stays open, so terminal output can race its worker.
  return (
    elements.some(
      (element) => element.key?.startsWith("grid:") && point(element),
    ) &&
    !elements.some(
      (element) =>
        element.focused ||
        element.key === "dialog" ||
        element.key === "menu-surface",
    )
  );
});

const keyboard = actions(() =>
  [
    "Tab",
    "Enter",
    "Backspace",
    "Delete",
    "Up",
    "Down",
    "Left",
    "Right",
    "Home",
    "End",
    "PageUp",
    "PageDown",
    " ",
  ].map((name) => ({ Key: { name } })),
);
// Rune edits byte-indexed UTF-8 text. Bias toward caret/deletion boundaries,
// not just appending more characters to a field forever.
const editing = actions(() => [
  ...["Home", "End", "Left", "Right", "Backspace", "Delete"].map((name) => ({
    Key: { name },
  })),
  ...[
    "e\u0301\u0327",
    "👩🏽‍💻🇳🇴",
    "אaب1",
    "\u2067abc\u2069",
    "\u0000\r\u001b",
    "\t".repeat(8),
    "\n\n",
  ].map((text) => ({ TypeText: { text } })),
]).when(() =>
  ui.current.elements.some(
    (element) =>
      live(element) &&
      element.focused &&
      element.role === "textbox" &&
      !element.inert,
  ),
);
const searchInput = actions(() =>
  [
    "zoo",
    "bash",
    " ",
    ".*",
    "no-zoo-match-93871",
    "e\u0301",
    "中",
    "👩🏽‍💻éאבג",
    ".*[\\](?i)",
    "a".repeat(512),
    "🦙éא".repeat(1024),
  ].map((text) => ({ TypeText: { text } })),
).when(() =>
  ui.current.elements.some(
    (field) =>
      live(field) &&
      field.focused &&
      !field.inert &&
      ui.current.elements.some(
        (search) =>
          live(search) &&
          search.key?.startsWith("search-field:") &&
          field.path.startsWith(`${search.path}/`),
      ),
  ),
);
// Steppers clamp at both limits. A separate budget makes repeated presses at
// a limit reachable without crowding out ordinary navigation.
const limitControls = actions(() =>
  ui.current.elements.flatMap((element) =>
    element.key &&
    /^(zoom|font|pane-padding)-(smaller|larger)$|^zoom-reset$/.test(
      element.key,
    ) &&
    point(element)
      ? [{ Tap: { key: element.key } }, { Tap: { key: element.key } }]
      : [],
  ),
);
// Change layout while a split tree exists. Coordinate clicks reach the
// repeated segment keys; keyed taps cannot distinguish Compact/Comfortable.
const layoutControls = actions(() => {
  const elements = ui.current.elements.filter(live);
  if (!elements.some((element) => element.key === "close-settings")) return [];
  const roots = elements.filter((element) =>
    ["pane-density", "tab-position"].includes(element.key ?? ""),
  );
  return elements.flatMap((element): ActionTemplate[] => {
    const at = point(element);
    if (!at) return [];
    const segment =
      element.role === "radio" &&
      roots.some((root) => element.path.startsWith(`${root.path}/`));
    const toggle = [
      "pane-header",
      "sidebar-switch",
      "chrome-theme",
      "terminal-theme",
    ].includes(element.key ?? "");
    const choice =
      element.role === "option" &&
      elements.some(
        (root) =>
          root.key === "menu-surface" &&
          element.path.startsWith(`${root.path}/`),
      );
    return segment || toggle || choice ? [{ Click: at }, { Click: at }] : [];
  });
});

const typing = actions(() => [
  ...[
    "",
    " ",
    "zoo",
    "blåbær 🦙 中文",
    "e\u0301",
    "אבג العربية",
    "\u200b\u200d\u2066text\u2069",
    "line one\nline two\tend",
    "\"'\\/<>&%",
    ".././~/.config/rex",
    "unix:///nonexistent-zoo-rex.sock",
    "https://127.0.0.1:1",
    "ssh://nobody@127.0.0.1:1",
    "9".repeat(128),
    "long label ".repeat(64),
  ].map((text) => ({ TypeText: { text } })),
  { TypeText: { text: string({ Text: [0, 128] }) } },
  { TypeText: { text: string({ Text: [256, 2048] }) } },
  { TypeText: { text: string({ Regexp: "[a-zA-Z0-9 ./_:@%+-]{1,128}" }) } },
]).when(() =>
  ui.current.elements.some(
    (element) =>
      element.focused && element.role === "textbox" && !element.inert,
  ),
);

const scrolling = actions(() =>
  ui.current.elements.flatMap((element) => {
    if (
      !element.key ||
      !/^(settings-scroll:|results-scroll$|sidebar-list$|grid:)/.test(
        element.key,
      )
    )
      return [];
    const at = point(element);
    return at
      ? [
          -100000, -2400, -600, -120, -1, -0.5, 0.5, 1, 120, 600, 2400, 100000,
        ].map((dy) => ({
          Scroll: { ...at, dy },
        }))
      : [];
  }),
);
const pointer = actions((): ActionTemplate[] => {
  const [width, height] = ui.current.viewport;
  // Leave the native titlebar alone; its controls are targeted above.
  return [
    { Click: { x: float([0, width - 0.01]), y: float([48, height - 0.01]) } },
    { Click: { x: 0, y: height - 1 } },
    { Click: { x: width - 1, y: height - 1 } },
    { Scroll: { x: width / 2, y: height / 2, dy: float([0, 2400]) } },
    { Scroll: { x: width / 2, y: height / 2, dy: -2400 } },
  ];
});

// Test both sides of clip, scrim and divider edges. Include inert controls
// under overlays: the pointer must hit the overlay, not its covered control.
const boundaryClicks = actions(() => {
  const [width, height] = ui.current.viewport;
  return ui.current.elements.flatMap((element): ActionTemplate[] => {
    if (
      !live(element) ||
      element.opacity <= 0 ||
      !element.key ||
      !/^(dialog$|menu-surface$|divider:|grid:|search:|search-field:|find-|pane-(header|close|split-|zoom:)|tab:|font-|zoom-|pane-padding-|settings-scroll:|results-scroll$|sidebar-list$)/.test(
        element.key,
      )
    )
      return [];
    const [x, y, w, h] = element.visible;
    if (w <= 0 || h <= 0) return [];
    return [-0.5, 0.5].flatMap((inset) =>
      [
        [x + inset, y + h / 2],
        [x + w - inset, y + h / 2],
        [x + w / 2, y + inset],
        [x + w / 2, y + h - inset],
      ]
        .filter(([px, py]) => px >= 0 && px < width && py >= 48 && py < height)
        .map(([px, py]) => ({ Click: { x: px, y: py } })),
    );
  });
});

export const interactions = weighted([
  [12, controls],
  [16, connectedControls],
  [20, splitDestruction],
  [14, commandSearch],
  [32, deepSplitPressure],
  [26, hostileLifecycle],
  [26, hostileCommandSearch],
  [18, workspaceChurn],
  [16, workspaceCommandSearch],
  [18, overlayPressure],
  [16, formSubmission],
  [16, terminalInput],
  [5, navigation],
  [4, recovery],
  [8, keyboard],
  [12, editing],
  [14, searchInput],
  [14, limitControls],
  [10, layoutControls],
  [6, typing],
  [12, scrolling],
  [5, pointer],
  [16, boundaryClicks],
]);
