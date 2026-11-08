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

    page.goto(f"{BASE}/fixture/zoo-repo/settings")
    expect(
        page.locator('input[name="repo_name"][data-repo-name="zoo-repo"]')
    ).to_have_value("zoo-repo")
    expect(page.locator('[data-signed-in-username="fixture"]')).to_have_count(1)
    page.screenshot(path="/tmp/artifacts/settings.png", full_page=True)
    browser.close()
