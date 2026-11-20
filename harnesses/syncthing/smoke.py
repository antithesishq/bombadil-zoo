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

    edit = page.locator('button[ng-click="editFolderExisting(folder)"]')
    # Use the same programmatic activation as the fuzz action. Lazy panel
    # visibility is not the behavior this editor persistence check measures.
    edit.evaluate("element => element.click()")
    folder_editor = page.locator("#editFolder")
    expect(folder_editor.locator(".modal-dialog")).to_be_visible()
    folder_editor.locator('a[href="#folder-ignores"]').click()
    patterns = folder_editor.locator('textarea[name="ignoresText"]')
    expect(patterns).to_be_editable()
    patterns.fill(
        "// Bombadil fixture\n*.tmp\n.cache/**\n**/backup-??.dat\n文档/**\n"
    )
    page.screenshot(path="/tmp/artifacts/ignores.png", full_page=True)
    patterns.press("Tab")
    with page.expect_response(
        lambda response: "/rest/db/ignores?" in response.url
        and response.request.method == "POST"
    ) as pending:
        folder_editor.locator('button[ng-click="saveFolder()"]').click()
    assert pending.value.ok
    assert "文档/**" in pending.value.request.post_data
    assert "**/backup-??.dat" in pending.value.request.post_data
    expect(folder_editor.locator(".modal-dialog")).not_to_be_visible()
    page.wait_for_function(
        "() => { const scope = angular.element(document.querySelector('#editFolder')).scope(); "
        "return scope && Object.keys(scope.ignores ?? {}).length === 0 "
        "&& !scope.currentFolder?._editing; }"
    )
    saved = page.evaluate(
        "async () => { const http = angular.element(document.body).injector().get('$http'); "
        "const response = await http.get('/rest/db/ignores?folder=zoo-sample'); "
        "return {status: response.status, body: response.data}; }"
    )
    print("ignore GET after save:", saved)
    assert saved["status"] == 200
    assert "文档/**" in saved["body"].get("ignore", [])
    assert "**/backup-??.dat" in saved["body"].get("ignore", [])
    with page.expect_response(
        lambda response: "/rest/db/ignores?" in response.url
        and response.request.method == "GET"
    ) as reopened:
        edit.evaluate("element => element.click()")
    print("ignore GET on editor reopen:", reopened.value.json())
    expect(folder_editor.locator(".modal-dialog")).to_be_visible()
    folder_editor.locator('a[href="#folder-ignores"]').click()
    expect(patterns).to_be_editable()
    expect(patterns).to_have_value(re.compile(r"文档/\*\*"))
    expect(patterns).to_have_value(re.compile(r"backup-\?\?\.dat"))
    folder_editor.locator('button[data-dismiss="modal"]').click()
    expect(folder_editor.locator(".modal-dialog")).not_to_be_visible()

    for width, height, name in [(360, 640, "mobile"), (1920, 1080, "wide")]:
        page.set_viewport_size({"width": width, "height": height})
        expect(
            page.locator("button.panel-heading").filter(has_text="Zoo Samples")
        ).to_be_visible()
        page.screenshot(
            path=f"/tmp/artifacts/dashboard-{name}.png", full_page=True
        )
    browser.close()
