"""Load the seeded dashboard, rescan it, and inspect real settings."""

import re

from playwright.sync_api import expect, sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path="/run/current-system/sw/bin/chromium",
        headless=True,
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto("http://127.0.0.1:8384/")
    expect(page).to_have_title(re.compile(r"\| Syncthing$"))
    expect(
        page.locator("button.panel-heading").filter(has_text="Zoo Samples")
    ).to_be_visible(timeout=60000)
    local_state = page.locator("#device-this tr").filter(
        has_text="Local State (Total)"
    )
    expect(local_state.locator("td")).to_contain_text(re.compile(r"\b3\b"))
    page.screenshot(path="/tmp/artifacts/dashboard.png", full_page=True)

    rescan = page.locator('button[ng-click="rescanAllFolders()"]')
    expect(rescan).to_be_visible()
    expect(rescan).to_be_enabled()
    with page.expect_response(
        lambda response: response.url.endswith("/rest/db/scan")
        and response.request.method == "POST"
    ) as pending:
        rescan.click()
    assert pending.value.ok

    actions = page.locator(".action-menu").filter(has_text="Actions")
    actions.locator("a.dropdown-toggle").click()
    actions.locator('a[ng-click="showSettings()"]').click()
    settings = page.locator("#settings")
    expect(settings.locator(".modal-dialog")).to_be_visible()
    expect(settings.locator("#DeviceName")).to_have_value("syncthing-zoo")
    settings.locator('a[href="#settings-gui"]').click()
    expect(settings.locator("#Address")).to_have_value("127.0.0.1:8384")
    page.screenshot(path="/tmp/artifacts/settings.png", full_page=True)
    settings.locator('button[data-dismiss="modal"]').click()
    expect(settings.locator(".modal-dialog")).not_to_be_visible()
    browser.close()
