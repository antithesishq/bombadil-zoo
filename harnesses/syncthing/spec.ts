import { always, eventually, now } from "@antithesishq/bombadil";
import {
  actions,
  extract,
  registerCustomAction,
  weighted,
} from "@antithesishq/bombadil/browser";
import { defaultActions } from "@antithesishq/bombadil/browser/defaults";
import { lastAction } from "@antithesishq/bombadil/browser/defaults/actions";

// Fuzzing can intentionally enter invalid settings or restart the server.
// Expected validation and transient connection messages are not target bugs.
export {
  noHttpErrorCodes,
  noUncaughtExceptions,
  noUnhandledPromiseRejections,
} from "@antithesishq/bombadil/browser/defaults";

function visible(element: Element | null): element is HTMLElement {
  return element instanceof HTMLElement && element.getClientRects().length > 0;
}

function uiReady(document: Document): boolean {
  return Array.from(
    document.querySelectorAll("button.panel-heading .panel-title-text"),
  ).some((heading) => {
    const text = heading.textContent?.trim() ?? "";
    return visible(heading) && text.length > 0 && !text.includes("{{");
  });
}

const page = extract(({ document, window }) => ({
  origin: window.location.origin,
  url: window.location.href,
  ready: uiReady(document),
  sampleFolder: Array.from(
    document.querySelectorAll("button.panel-heading .panel-title-text"),
  ).some(
    (heading) =>
      visible(heading) && heading.textContent?.trim() === "Zoo Samples",
  ),
  dialog: visible(document.querySelector(".modal.fade.in")),
}));

export const staysLocal = always(
  () =>
    page.current.origin === "http://127.0.0.1:8384" ||
    // A parallel run can restart Syncthing while this run reloads. Chrome's
    // internal error page is not remote navigation; reloadRecovers still applies.
    page.current.url.startsWith("chrome-error://chromewebdata/"),
);
export const uiLoads = eventually(() => page.current.ready).within(
  20,
  "seconds",
);
export const reloadRecovers = always(
  now(() => lastAction.current === "Reload").implies(
    eventually(() => page.current.ready).within(20, "seconds"),
  ),
);

const waitForUI = registerCustomAction(
  "syncthing-wait-for-ui",
  async (document, window) => {
    // Keep yielding states so uiLoads can diagnose a startup timeout.
    if (!uiReady(document)) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, 100));
    }
  },
);

const rescanFolder = registerCustomAction(
  "syncthing-rescan-folder",
  async (document, window) => {
    if (visible(document.querySelector(".modal.fade.in"))) return;
    const heading = Array.from(
      document.querySelectorAll<HTMLButtonElement>(
        'button.panel-heading[data-target^="#folder-"]',
      ),
    ).find((button) => visible(button));
    const selector = heading?.getAttribute("data-target");
    if (!heading || !selector) return;
    const panel = document.querySelector<HTMLElement>(selector);
    if (!panel) return;

    // Generic clicks rarely expand a folder before choosing its footer. Bound
    // each wait so a removed folder or a concurrent restart cannot hang a run.
    if (!panel.classList.contains("in")) {
      heading.click();
      for (let i = 0; i < 40 && !panel.classList.contains("in"); i++) {
        await new Promise<void>((resolve) => window.setTimeout(resolve, 50));
      }
    }
    if (!panel.classList.contains("in")) return;

    const resume = panel.querySelector<HTMLButtonElement>(
      'button[ng-click="setFolderPause(folder.id, false)"]',
    );
    if (resume && !resume.disabled) {
      resume.click();
      for (let i = 0; i < 40 && document.contains(resume); i++) {
        await new Promise<void>((resolve) => window.setTimeout(resolve, 50));
      }
    }
    const rescan = panel.querySelector<HTMLButtonElement>(
      'button[ng-click="rescanFolder(folder.id)"]',
    );
    if (rescan && !rescan.disabled) rescan.click();
  },
);

const exploreFolder = registerCustomAction(
  "syncthing-explore-folder-settings",
  async (document, window) => {
    if (visible(document.querySelector(".modal.fade.in"))) return;
    const heading = document.querySelector<HTMLButtonElement>(
      'button.panel-heading[data-target^="#folder-"]',
    );
    if (!heading) return;
    const panel = document.querySelector<HTMLElement>(
      heading.getAttribute("data-target") ?? "",
    );
    if (!panel) return;
    if (!panel.classList.contains("in")) {
      heading.click();
      for (let i = 0; i < 40 && !panel.classList.contains("in"); i++) {
        await new Promise<void>((resolve) => window.setTimeout(resolve, 50));
      }
    }
    const edit = panel.querySelector<HTMLButtonElement>(
      'button[ng-click="editFolderExisting(folder)"]',
    );
    if (!edit) return;
    edit.click();
    for (let i = 0; i < 40; i++) {
      const modal = document.querySelector<HTMLElement>("#editFolder");
      if (visible(modal)) break;
      await new Promise<void>((resolve) => window.setTimeout(resolve, 50));
    }
    // Do not save: let generic form input mutate the existing folder after
    // reaching controls that generic clicks rarely visit in sequence.
    for (const tab of ["#folder-sharing", "#folder-versioning", "#folder-general"]) {
      document.querySelector<HTMLAnchorElement>(`a[href="${tab}"]`)?.click();
    }
  },
);

const interaction = weighted([
  [1, rescanFolder()],
  [1, exploreFolder()],
  // Keep startup waits replayable when reproduction reaches the UI sooner.
  [1, waitForUI()],
  [4, defaultActions],
]);

export const explore = actions(() =>
  page.current.ready ? interaction.generate() : [waitForUI()],
);
