import { always } from "@antithesishq/bombadil";
import { actions, extract, integer } from "@antithesishq/bombadil/external";

type Entry = { SYSLOG_IDENTIFIER?: string; PRIORITY?: string; MESSAGE?: string };
type State = {
  appAlive: boolean;
  windows: { app_id: string; rect: { x: number; y: number; width: number; height: number } }[];
  logs: { complete: boolean; entries: Entry[] };
};
const desktop = extract((state: State) => state);

// Properties

export const appStaysAlive = always(() => desktop.current.appAlive);
export const logsAvailable = always(() => desktop.current.logs.complete);
// The target never logs at error level or worse (syslog priority 0-3).
export const noTargetErrors = always(() => !desktop.current.logs.entries.some((e) =>
  e.SYSLOG_IDENTIFIER === "hokum-target" && Number(e.PRIORITY ?? 6) <= 3));

// Actions

// Keyboard navigation, and clicks anywhere inside the app's windows. Rune
// exposes no accessibility tree, so targets are window coordinates.
const keys = ["Tab", "Enter", "Escape", " ", "Left", "Right", "Up", "Down", "Home", "End"]
  .map((name) => ({ Key: { name } }));

export const interact = actions(() => [
  ...keys,
  ...desktop.current.windows.map(({ rect: r }) => ({
    Click: { x: integer([r.x, r.x + r.width - 1]), y: integer([r.y, r.y + r.height - 1]) },
  })),
]);
