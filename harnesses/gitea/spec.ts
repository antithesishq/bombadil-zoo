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

function elementPoint(element: Element | null): { x: number; y: number } | null {
  const rect = element?.getBoundingClientRect();
  return rect
    ? { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 }
    : null;
}

function navigationPoint(document: Document): { x: number; y: number } | null {
  return elementPoint(document.querySelector("#gitea-zoo-navigation"));
}

const page = extract(({ document, window }) => ({
  origin: window.location.origin,
  path: window.location.pathname,
  ready:
    document.querySelector("#navbar") !== null &&
    (document.body.textContent ?? "").trim().length > 0,
  hasContent: (document.body.textContent ?? "").trim().length > 0,
  navigation: navigationPoint(document),
  issueSubmit: elementPoint(document.querySelector("#gitea-zoo-issue-submit")),
  login: document.querySelector('form input[name="user_name"]') !== null,
  credentialsReady:
    document.querySelector<HTMLInputElement>('input[name="user_name"]')
      ?.value === "fixture" &&
    document.querySelector<HTMLInputElement>('input[name="password"]')?.value ===
      "zoo-fixture-password",
  signedIn:
    document.querySelector('[data-signed-in-username="fixture"]') !== null,
  repository: document.querySelector(".page-content.repository") !== null,
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
export const uiLoads = eventually(
  () => page.current.ready && (page.current.login || page.current.signedIn),
).within(15, "seconds");
export const reloadRecovers = always(
  now(() => lastAction.current === "Reload").implies(
    eventually(
      () => page.current.ready && (page.current.login || page.current.signedIn),
    ).within(15, "seconds"),
  ),
);

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

const prepareNavigation = registerCustomAction(
  "gitea-prepare-navigation",
  async (document, _window, path: string) => {
    document.querySelector("#gitea-zoo-navigation")?.remove();
    const link = document.createElement("a");
    link.id = "gitea-zoo-navigation";
    link.href = path;
    link.textContent = "Fixture navigation";
    link.style.cssText =
      "position:fixed;left:8px;top:8px;z-index:99999;" +
      "padding:4px;background:white;color:black";
    document.body.appendChild(link);
  },
);

const prepareIssue = registerCustomAction(
  "gitea-prepare-issue",
  async (document, _window) => {
    const content = document.querySelector<HTMLTextAreaElement>(
      'textarea[name="content"]',
    );
    if (!content?.getClientRects().length || !content.form) return;
    const title = document.querySelector<HTMLInputElement>('input[name="title"]');
    if (title?.getClientRects().length) {
      title.value = "Fuzzed issue: Markdown, Unicode and form state";
      title.dispatchEvent(new Event("input", { bubbles: true }));
    }
    content.value =
      "A fuzzed **comment** with `code`.\n\n- one\n- two\n\n> blåbær 🦙 中文\n";
    content.dispatchEvent(new Event("input", { bubbles: true }));
    const submit = Array.from(
      content.form.querySelectorAll<HTMLButtonElement>('button[type="submit"]'),
    ).find((button) =>
      ["Comment", "Create Issue"].includes(button.textContent?.trim() ?? ""),
    );
    if (submit && !submit.disabled) submit.id = "gitea-zoo-issue-submit";
  },
);

const waitForUI = registerCustomAction(
  "gitea-wait-for-ui",
  async (_document, window) => {
    await new Promise<void>((resolve) => window.setTimeout(resolve, 100));
  },
);

const fixtureNavigation = actions(() =>
  [
    "/fixture/zoo-repo",
    "/fixture/zoo-repo/src/branch/main/docs/guide.md",
    "/fixture/zoo-repo/commits/branch/main",
    "/fixture/zoo-repo/issues",
    "/fixture/zoo-repo/issues/1",
    "/fixture/zoo-repo/issues/new",
    "/fixture/zoo-repo/settings",
  ].map((path) => prepareNavigation(path)),
);
const interaction = weighted([
  [3, defaultActions],
  [1, fixtureNavigation],
  [1, prepareIssue()],
]);
const issueFingerprint = {
  testId: null,
  id: "gitea-zoo-issue-submit",
  role: null,
  accessibleName: null,
  tag: "button",
  href: null,
  nameAttr: null,
  placeholder: null,
  inputType: null,
  textContent: null,
  structuralPath: null,
} as const;
const navigationFingerprint = {
  testId: null,
  id: "gitea-zoo-navigation",
  role: null,
  accessibleName: null,
  tag: "a",
  href: null,
  nameAttr: null,
  placeholder: null,
  inputType: null,
  textContent: null,
  structuralPath: null,
} as const;

export const explore = actions(() => {
  if (page.current.login) {
    return page.current.credentialsReady
      ? [{ PressKey: { code: 13 } }]
      : [login()];
  }
  const issuePoint = page.current.issueSubmit;
  if (issuePoint) {
    return [{ Click: { fingerprint: issueFingerprint, point: issuePoint } }];
  }
  const point = page.current.navigation;
  if (point) {
    // Native clicking avoids destroying a custom action's execution context
    // while its own promise is still being awaited.
    return [
      {
        Click: { fingerprint: navigationFingerprint, point },
      },
    ];
  }
  if (!page.current.ready) {
    // Swagger and plain-text auxiliary pages do not have Gitea's navbar.
    // Recover from them instead of waiting for an impossible selector.
    return page.current.hasContent
      ? [prepareNavigation("/fixture/zoo-repo")]
      : [waitForUI()];
  }
  return interaction.generate();
});
