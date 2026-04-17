import logging
from playwright.async_api import async_playwright, Browser, Playwright

logger = logging.getLogger(__name__)

_playwright: Playwright | None = None
_browser: Browser | None = None


async def get_browser() -> Browser:
    global _playwright, _browser
    if _browser is None or not _browser.is_connected():
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
        logger.info("Playwright browser launched")
    return _browser


async def close_browser() -> None:
    global _playwright, _browser
    if _browser and _browser.is_connected():
        await _browser.close()
        _browser = None
        logger.info("Playwright browser closed")
    if _playwright:
        await _playwright.stop()
        _playwright = None
