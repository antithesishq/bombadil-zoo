import { always } from "@antithesishq/bombadil";
import {
  actions,
  extract,
  registerCustomAction,
} from "@antithesishq/bombadil/browser";
import { defaultActions } from "@antithesishq/bombadil/browser/defaults";

// Expected form-validation errors are not necessarily application failures.
export {
  noUncaughtExceptions,
  noUnhandledPromiseRejections,
} from "@antithesishq/bombadil/browser/defaults";

const page = extract(({ document, window }) => ({
  login: document.querySelector('input[name="api_key"]') !== null,
  origin: window.location.origin,
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

const login = registerCustomAction(
  "headplane-login",
  async (document, window, key: string) => {
    const input = document.querySelector<HTMLInputElement>(
      'input[name="api_key"]',
    );
    if (!input?.form) return;
    input.value = key;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.form.requestSubmit();
    // Do not flood the form with submissions while React Router is navigating.
    for (let i = 0; i < 100 && document.contains(input); i++) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, 50));
    }
  },
);

export const explore = actions(() =>
  page.current.login
    ? [login("__HEADPLANE_API_KEY__")]
    : defaultActions.generate(),
);
