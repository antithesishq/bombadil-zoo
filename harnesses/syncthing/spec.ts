import { always, eventually, now } from "@antithesishq/bombadil";
import {
  actions,
  extract,
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
export const resizeRecovers = always(
  now(
    () =>
      typeof lastAction.current === "object" &&
      lastAction.current !== null &&
      "SetViewport" in lastAction.current,
  ).implies(eventually(() => page.current.ready).within(20, "seconds")),
);

// Any viewport from a phone to a desktop monitor, within a run.
const viewportSizes = actions(() => [
  { SetViewport: { width: [360, 1920], height: [640, 1080] } },
]);

const interaction = weighted([
  [4, defaultActions],
  [1, viewportSizes],
]);

export const explore = actions(() =>
  page.current.ready ? interaction.generate() : ["Wait"],
);
