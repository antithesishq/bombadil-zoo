"""Exercise the public UI before fuzzing, including a persisted mutation."""

from pathlib import Path

from playwright.sync_api import expect, sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path="/run/current-system/sw/bin/chromium",
        headless=True,
        args=["--no-sandbox"],
    )
    page = browser.new_page()
    page.goto("http://127.0.0.1:3000/admin/login")
    page.locator('input[name="api_key"]').fill("invalid-zoo-key")
    page.locator('button[type="submit"]').click()
    expect(page.locator('input[name="api_key"]')).to_be_visible()
    expect(page.get_by_text("API key is invalid", exact=False)).to_be_visible()
    page.locator('input[name="api_key"]').fill(
        Path("/var/lib/zoo/api-key").read_text().strip()
    )
    page.locator('button[type="submit"]').click()
    page.wait_for_url("**/machines")
    page.screenshot(path="/tmp/artifacts/machines.png", full_page=True)
    page.goto("http://127.0.0.1:3000/admin/users")
    page.get_by_role("button", name="Add user", exact=True).click()
    page.locator('input[name="username"]').fill("smoke-created")
    page.locator('input[name="display_name"]').fill("Smoke Created")
    page.locator('input[name="email"]').fill("smoke@example.test")
    page.locator('button[type="submit"]').click()
    expect(page.get_by_text("smoke-created", exact=True)).to_be_visible()
    page.reload()
    expect(page.get_by_text("smoke-created", exact=True)).to_be_visible()
    page.screenshot(path="/tmp/artifacts/users.png", full_page=True)
    browser.close()
