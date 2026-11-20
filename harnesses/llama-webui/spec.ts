import { always, eventually, now } from "@antithesishq/bombadil";
import {
  actions,
  extract,
  registerCustomAction,
  weighted,
} from "@antithesishq/bombadil/browser";
import {
  clicks,
  inputs,
  lastAction,
  navigation,
  scroll,
  waitOnce,
} from "@antithesishq/bombadil/browser/defaults/actions";

// Invalid JSON settings and unsupported model inputs can produce handled errors.
// Check application failures, not every console message or rejected API request.
export {
  noUncaughtExceptions,
  noUnhandledPromiseRejections,
  noHttpErrorCodes,
} from "@antithesishq/bombadil/browser/defaults";

function composerInput(document: Document): HTMLElement | null {
  const dialog = document.querySelector('[role="dialog"]');
  if (dialog?.getClientRects().length) return null;
  const input = document.querySelector<HTMLElement>(
    ".chat-screen-form-wrapper form textarea:not(:disabled), " +
      '.chat-screen-form-wrapper form [contenteditable="true"]',
  );
  return input?.getClientRects().length ? input : null;
}

const page = extract(({ document, window }) => {
  const composer = composerInput(document);
  return {
    origin: window.location.origin,
    ready: document.querySelector("aside, .chat-screen-form-wrapper") !== null,
    composer: composer !== null,
    composing: composer !== null && composer.contains(document.activeElement),
    generating: Array.from(document.querySelectorAll("button")).some(
      (button) =>
        button.textContent?.trim() === "Stop" ||
        button.getAttribute("aria-label") === "Stop generation",
    ),
  };
});

// Properties

export const staysLocal = always(
  () => page.current.origin === "http://127.0.0.1:8080",
);
export const uiLoads = eventually(() => page.current.ready).within(
  15,
  "seconds",
);
export const generationCompletes = always(
  now(() => page.current.generating).implies(
    eventually(() => !page.current.generating).within(15, "seconds"),
  ),
);
export const reloadRecovers = always(
  now(() => lastAction.current === "Reload").implies(
    eventually(() => page.current.ready).within(15, "seconds"),
  ),
);

// Actions

const focusComposer = registerCustomAction(
  "llama-focus-composer",
  async (document) => composerInput(document)?.focus(),
);

// With the composer focused: generated text (ASCII, Markdown-ish symbols,
// any printable Unicode) and Enter to send.
const composing = weighted([
  [4, { TypeText: { text: { Regexp: "[ -~]{1,80}" } } }],
  [2, { TypeText: { text: { Regexp: "[-#*_`|$>\\[\\]() a-z0-9\n]{1,120}" } } }],
  [1, { TypeText: { text: { Regexp: "\\PC{1,80}" } } }],
  [3, { PressKey: { code: 13 } }],
]);

// Keep menus in the mix, but spend more actions writing and sending chats.
const interaction = weighted([
  [3, clicks],
  [3, inputs],
  [2, focusComposer()],
  [1, scroll],
  [1, navigation],
  [1, waitOnce],
]);
export const explore = actions(() => {
  if (!page.current.ready) return ["Wait"];
  return page.current.composing
    ? weighted([[2, composing], [1, interaction]]).generate()
    : interaction.generate();
});
