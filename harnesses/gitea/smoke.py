"""Log in through the real Web UI and inspect seeded repository state."""

import re

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:3000"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path="/run/current-system/sw/bin/chromium",
        headless=True,
        args=["--no-sandbox"],
    )
    page = browser.new_page(
        viewport={"width": 1280, "height": 800}, locale="en-US"
    )
    page.goto(f"{BASE}/user/login")
    page.locator('input[name="user_name"]').fill("fixture")
    page.locator('input[name="password"]').fill("zoo-fixture-password")
    page.get_by_role("button", name="Sign In", exact=True).click()
    page.wait_for_url(lambda url: not url.endswith("/user/login"))
    expect(page.locator('[data-signed-in-username="fixture"]')).to_have_count(1)

    page.goto(f"{BASE}/fixture/zoo-repo")
    expect(page).to_have_title(re.compile(r"zoo-repo - Bombadil Gitea Zoo$"))
    expect(page.locator("#readme")).to_contain_text("Bombadil Gitea fixture")
    expect(page.get_by_role("link", name="docs", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="src", exact=True)).to_be_visible()
    page.screenshot(path="/tmp/artifacts/repository.png", full_page=True)

    page.goto(f"{BASE}/fixture/zoo-repo/issues/1")
    expect(
        page.get_by_role(
            "heading", name=re.compile(r"Review seeded documentation #1")
        )
    ).to_be_visible()
    expect(
        page.get_by_role("paragraph").filter(
            has_text="A harmless issue for browser exploration"
        )
    ).to_be_visible()
    page.screenshot(path="/tmp/artifacts/issue.png", full_page=True)

    page.goto(f"{BASE}/fixture/zoo-repo/_edit/main/docs/guide.md")
    editor = page.locator(".cm-content")
    expect(editor).to_be_visible(timeout=30000)
    editor.evaluate(
        "el => { el.focus(); const range = el.ownerDocument.createRange(); "
        "range.selectNodeContents(el); const selection = el.ownerDocument.getSelection(); "
        "selection.removeAllRanges(); selection.addRange(range); }"
    )
    text = (
        "# Fixture guide\n\nEdited by Bombadil: **blåbær 🦙**.\n\n"
        "- [ ] exercise the editor\n- [x] render Markdown\n"
    )
    for char in text:
        page.keyboard.insert_text(char)
    page.locator('input[name="commit_summary"]').fill(
        "Update fixture guide with fuzzed content"
    )
    page.locator('textarea[name="commit_message"]').fill(
        "Exercise CodeMirror editing and the commit form."
    )
    commit = page.locator("#commit-button")
    expect(commit).to_be_enabled()
    page.screenshot(path="/tmp/artifacts/file-editor.png", full_page=True)
    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/_edit/main/docs/guide.md")
    ) as pending:
        commit.click()
    assert pending.value.status < 400
    page.wait_for_url(lambda url: "/_edit/" not in url)
    page.goto(f"{BASE}/fixture/zoo-repo/src/branch/main/docs/guide.md")
    expect(page.locator("body")).to_contain_text("Edited by Bombadil:")

    page.goto(f"{BASE}/fixture/zoo-repo/settings")
    expect(
        page.locator('input[name="repo_name"][data-repo-name="zoo-repo"]')
    ).to_have_value("zoo-repo")
    expect(page.locator('[data-signed-in-username="fixture"]')).to_have_count(1)
    page.screenshot(path="/tmp/artifacts/settings.png", full_page=True)
    for width, height, name in [(360, 640, "mobile"), (1920, 1080, "wide")]:
        page.set_viewport_size({"width": width, "height": height})
        expect(
            page.locator('input[name="repo_name"][data-repo-name="zoo-repo"]')
        ).to_be_visible()
        page.screenshot(
            path=f"/tmp/artifacts/settings-{name}.png", full_page=True
        )
    browser.close()
