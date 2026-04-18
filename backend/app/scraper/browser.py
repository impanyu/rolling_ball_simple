import logging
from playwright.async_api import async_playwright, Browser, Playwright

logger = logging.getLogger(__name__)

_playwright: Playwright | None = None
_browser: Browser | None = None


async def get_browser() -> Browser:
    global _playwright, _browser
    if _browser is None or not _browser.is_connected():
        # Close stale instances first
        if _browser:
            try:
                await _browser.close()
            except Exception:
                pass
            _browser = None
        if _playwright:
            try:
                await _playwright.stop()
            except Exception:
                pass
            _playwright = None

        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
        logger.info("Playwright browser launched")
    return _browser


async def close_browser() -> None:
    global _playwright, _browser
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
        logger.info("Playwright browser closed")
    if _playwright:
        try:
            await _playwright.stop()
        except Exception:
            pass
        _playwright = None
