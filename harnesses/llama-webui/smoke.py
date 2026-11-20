"""Check real streamed inference, conversation persistence and settings."""

import re

from playwright.sync_api import expect, sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path="/run/current-system/sw/bin/chromium",
        headless=True,
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto("http://127.0.0.1:8080/")
    composer = page.locator(".chat-screen-form-wrapper").get_by_role("textbox")
    prompt = "Once upon a time there was a little llama."
    composer.fill(prompt)
    send = page.get_by_role("button", name="Send", exact=True)
    expect(send).to_be_enabled()
    with page.expect_response(
        lambda response: response.url.endswith("/v1/chat/completions")
        and response.request.method == "POST"
    ) as pending:
        send.click()
    response = pending.value
    assert response.ok
    assert "text/event-stream" in response.headers["content-type"]
    assert response.request.post_data_json["stream"] is True
    assert response.finished() is None
    answer = page.get_by_role(
        "group", name="Assistant message with actions", exact=True
    ).last.locator(".agentic-text")
    expect(answer).not_to_have_text("", timeout=60000)
    expect(page.get_by_role("button", name="Stop", exact=True)).to_have_count(0)
    saved_answer = answer.inner_text()
    saved_url = page.url
    assert "/chat/" in saved_url
    page.reload()
    expect(page).to_have_url(saved_url)
    expect(
        page.get_by_role(
            "group", name="User message with actions", exact=True
        ).get_by_text(prompt, exact=True)
    ).to_be_visible()
    expect(answer).to_have_text(saved_answer)
    page.screenshot(path="/tmp/artifacts/chat.png", full_page=True)
    page.get_by_role("button", name=re.compile(r"^Settings")).click()
    settings = page.get_by_role("dialog", name="Settings", exact=True)
    expect(settings).to_be_visible()
    page.screenshot(path="/tmp/artifacts/settings.png", full_page=True)
    settings.get_by_role("button", name="Close", exact=True).click()
    browser.close()
