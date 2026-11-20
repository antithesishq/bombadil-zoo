import { always, eventually, now } from "@antithesishq/bombadil";
import {
  actions,
  extract,
  registerCustomAction,
  weighted,
} from "@antithesishq/bombadil/browser";
import { defaultActions } from "@antithesishq/bombadil/browser/defaults";
import { lastAction } from "@antithesishq/bombadil/browser/defaults/actions";

// Random form submissions can produce handled validation errors and 4xx pages.
// Check application failures and server errors, not every HTTP error response.
export {
  noUncaughtExceptions,
  noUnhandledPromiseRejections,
} from "@antithesishq/bombadil/browser/defaults";

const page = extract(({ document, window }) => ({
  origin: window.location.origin,
  ready:
    document.querySelector("#navbar") !== null &&
    (document.body.textContent ?? "").trim().length > 0,
  hasContent: (document.body.textContent ?? "").trim().length > 0,
  login: document.querySelector('form input[name="user_name"]') !== null,
  credentialsReady:
    document.querySelector<HTMLInputElement>('input[name="user_name"]')
      ?.value === "fixture" &&
    document.querySelector<HTMLInputElement>('input[name="password"]')?.value ===
      "zoo-fixture-password",
  signedIn:
    document.querySelector('[data-signed-in-username="fixture"]') !== null,
  status:
    (
      window.performance.getEntriesByType(
        "navigation",
      )[0] as PerformanceNavigationTiming
    )?.responseStatus ?? 0,
}));

export const staysLocal = always(
  () => page.current.origin === "http://127.0.0.1:3000",
);
export const noServerError = always(() => page.current.status < 500);
const usable = () =>
  page.current.ready && (page.current.login || page.current.signedIn);
const resized = () =>
  typeof lastAction.current === "object" &&
  lastAction.current !== null &&
  "SetViewport" in lastAction.current;
export const uiLoads = eventually(usable).within(15, "seconds");
export const reloadRecovers = always(
  now(() => lastAction.current === "Reload").implies(
    eventually(usable).within(15, "seconds"),
  ),
);
export const resizeRecovers = always(
  now(resized).implies(eventually(usable).within(15, "seconds")),
);

// Any viewport from a phone to a desktop monitor, within a run.
const viewportSizes = actions(() => [
  { SetViewport: { width: [360, 1920], height: [640, 1080] } },
]);

const login = registerCustomAction(
  "gitea-login",
  async (document, _window) => {
    const input = document.querySelector<HTMLInputElement>(
      'form input[name="user_name"]',
    );
    const password = document.querySelector<HTMLInputElement>(
      'form input[name="password"]',
    );
    const form = input?.form;
    if (!input || !password || !form || password.form !== form) return;
    input.value = "fixture";
    password.value = "zoo-fixture-password";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    password.dispatchEvent(new Event("input", { bubbles: true }));
    // A native Enter action submits the form on the next step. Starting a
    // navigation inside this JavaScript action can strand the action's promise
    // when its execution context is replaced.
    password.focus();
  },
);

const interaction = weighted([
  [4, defaultActions],
  [1, viewportSizes],
]);
export const explore = actions(() => {
  if (page.current.login) {
    return page.current.credentialsReady
      ? [{ PressKey: { code: 13 } }]
      : [login()];
  }
  if (!page.current.ready) {
    // Swagger and plain-text auxiliary pages do not have Gitea's navbar.
    // Go back from them instead of waiting for an impossible selector.
    return page.current.hasContent ? ["Back"] : ["Wait"];
  }
  return interaction.generate();
});
