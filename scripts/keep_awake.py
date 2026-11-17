"""Keep the Streamlit app awake.

Streamlit Community Cloud puts an app to sleep after 12 hours without
visitors. A plain HTTP request does not count: the app only runs when a
browser opens it. So this opens the app in a real (headless) browser, clicks
"Yes, get this app back up!" if the app is asleep, and waits until the app
has actually loaded. Run on a schedule by .github/workflows/keep-awake.yml.

Usage: python scripts/keep_awake.py [url]
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://azimuth-launch.streamlit.app/"
LOADED_TEXT = "Market Overview"   # shown by the app once it is running
WAKE_BUTTON = "Yes, get this app back up!"


def annotate(level, message):
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level} title=Keep awake::{message}")
    else:
        print(message)


def app_loaded(page):
    """The app runs inside a frame; look for its text in every frame."""
    for frame in page.frames:
        try:
            if LOADED_TEXT in frame.inner_text("body", timeout=2000):
                return True
        except Exception:
            pass
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(10_000)

        woke = False
        button = page.get_by_role("button", name=WAKE_BUTTON)
        if button.count():
            button.first.click()
            woke = True

        # starting from sleep can take a few minutes
        deadline = time.time() + (300 if woke else 120)
        while time.time() < deadline and not app_loaded(page):
            page.wait_for_timeout(5_000)
        loaded = app_loaded(page)
        # stay a little, as a visitor would
        page.wait_for_timeout(10_000)
        browser.close()

    if loaded:
        annotate("notice", "The app was asleep and has been woken up." if woke
                 else "The app is awake.")
    else:
        annotate("error", f"The app did not load within the time allowed{' after waking it' if woke else ''}.")
        sys.exit(1)


if __name__ == "__main__":
    main()
