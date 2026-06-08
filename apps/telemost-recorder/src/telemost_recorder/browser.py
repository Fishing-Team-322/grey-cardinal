from __future__ import annotations

import logging

from playwright.async_api import Browser, Page, async_playwright

logger = logging.getLogger(__name__)


class TelemostBrowser:
    def __init__(self, participant_name: str, join_timeout_seconds: int) -> None:
        self.participant_name = participant_name
        self.join_timeout_ms = join_timeout_seconds * 1000
        self._playwright = None
        self._browser: Browser | None = None
        self.page: Page | None = None

    async def join(self, url: str) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--autoplay-policy=no-user-gesture-required",
                "--use-fake-ui-for-media-stream",
            ],
        )
        context = await self._browser.new_context(ignore_https_errors=True)
        self.page = await context.new_page()
        await self.page.goto(url, wait_until="domcontentloaded", timeout=self.join_timeout_ms)

        continue_button = self.page.get_by_role("button", name="Продолжить в браузере")
        if await continue_button.count() and await continue_button.is_visible():
            await continue_button.click()

        await self._dismiss_known_dialogs()
        name_input = self.page.get_by_role("textbox")
        await name_input.wait_for(state="visible", timeout=self.join_timeout_ms)
        await name_input.fill(self.participant_name)
        await self._ensure_muted()

        connect_button = self.page.get_by_role("button", name="Подключиться", exact=True)
        await connect_button.click()
        await connect_button.wait_for(state="hidden", timeout=self.join_timeout_ms)
        logger.info("Joined Telemost as visible participant %s", self.participant_name)

    async def _dismiss_known_dialogs(self) -> None:
        for _ in range(3):
            button = self.page.get_by_role("button", name="Понятно", exact=True)
            if await button.count() == 0:
                return
            await button.first.click()

    async def _ensure_muted(self) -> None:
        for enabled_name in ("Выключить микрофон", "Выключить камеру"):
            button = self.page.get_by_role("button", name=enabled_name, exact=True)
            if await button.count():
                await button.click()

    async def meeting_ended(self) -> bool:
        if self.page is None or self.page.is_closed():
            return True
        for text in ("Встреча завершена", "Организатор завершил встречу"):
            if await self.page.get_by_text(text, exact=False).count():
                return True
        return False

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
