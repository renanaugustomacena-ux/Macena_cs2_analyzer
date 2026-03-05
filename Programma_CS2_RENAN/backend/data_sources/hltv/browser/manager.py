from playwright.sync_api import sync_playwright


class BrowserManager:
    def __init__(self, headless=True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None

    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless, args=_get_browser_args()
        )
        self.context = self.browser.new_context(
            user_agent=_get_user_agent(), viewport={"width": 1920, "height": 1080}
        )
        return _setup_new_page(self.context)

    def close(self):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    # F6-08: Context manager protocol — prevents browser resource leaks on exceptions.
    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # Do not suppress exceptions


def _get_browser_args():
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
    ]


def _get_user_agent():
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"


# COMPLIANCE NOTE: The webdriver property override below disables browser automation
# detection signals. This may conflict with HLTV's Terms of Service. Before enabling
# HLTV scraping in production:
#   1. Review HLTV ToS for automated access restrictions.
#   2. Consider the official HLTV API or third-party data providers as alternatives.
#   3. Ensure rate limiting (RateLimiter) is enforced to avoid abusive traffic.
# F6-02: This file requires explicit ToS compliance sign-off before production use.
def _setup_new_page(context):
    page = context.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return page
