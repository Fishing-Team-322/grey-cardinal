from __future__ import annotations

import logging
from pathlib import Path

from playwright.async_api import BrowserContext, Page, TimeoutError as PWTimeout, async_playwright

from .config import Settings

logger = logging.getLogger(__name__)

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--autoplay-policy=no-user-gesture-required",
    "--use-fake-ui-for-media-stream",
    "--disable-blink-features=AutomationControlled",
]


class TelemostBrowser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.participant_name = settings.participant_name
        self.join_timeout_ms = settings.join_timeout_seconds * 1000
        self._playwright = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def _ensure_context(self) -> None:
        if self._context is not None:
            return
        self._playwright = await async_playwright().start()
        Path(self.settings.user_data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.settings.screenshot_dir).mkdir(parents=True, exist_ok=True)
        # Persistent context keeps the Yandex session cookies between meetings
        # and restarts, so we only log in once.
        self._context = await self._playwright.chromium.launch_persistent_context(
            self.settings.user_data_dir,
            headless=False,
            args=LAUNCH_ARGS,
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 1024},
            locale="ru-RU",
        )
        self.page = self._context.pages[0] if self._context.pages else await self._context.new_page()

    async def _shot(self, name: str) -> None:
        if self.page is None:
            return
        try:
            path = Path(self.settings.screenshot_dir) / f"{name}.png"
            await self.page.screenshot(path=str(path), full_page=False)
            logger.info("Saved screenshot %s", path)
        except Exception:
            logger.debug("Could not save screenshot %s", name, exc_info=True)

    # ── Yandex auth ────────────────────────────────────────────────────────

    async def ensure_logged_in(self) -> None:
        """Make sure the persistent profile holds a valid Yandex session.

        No-op when already authenticated (cookies persisted from a prior run).
        """
        await self._ensure_context()
        assert self.page is not None
        if not self.settings.yandex_login or not self.settings.yandex_password:
            logger.warning("No Yandex credentials configured — joining anonymously")
            return

        await self.page.goto(
            "https://passport.yandex.ru/profile",
            wait_until="domcontentloaded",
            timeout=self.join_timeout_ms,
        )
        await self.page.wait_for_timeout(1000)
        # When already authenticated, Yandex serves the profile (possibly on
        # id.yandex.ru); only an unauthenticated session lands on an auth /
        # passwordless (pwl) page.
        if "/auth" not in self.page.url and "/pwl" not in self.page.url:
            logger.info("Yandex session already active (%s)", self.page.url)
            return

        logger.info("Logging into Yandex as %s", self.settings.yandex_login)
        try:
            await self._do_login()
        except Exception:
            await self._shot("login-error")
            raise

    async def _do_login(self) -> None:
        assert self.page is not None
        page = self.page
        if "/auth" not in page.url:
            await page.goto(
                "https://passport.yandex.ru/auth",
                wait_until="domcontentloaded",
                timeout=self.join_timeout_ms,
            )

        # Step 1: login / email. Yandex now defaults to a passwordless (phone /
        # passkey) screen; the login+password field is hidden behind
        # "Ещё" → "Войти по логину". The login input has no stable name, so match
        # it by placeholder ("Логин или email") — the phone field has none.
        login_field = page.locator(
            "input[name='login'], input[placeholder*='огин']"
        ).first
        await self._reveal_login_field(login_field)
        await login_field.wait_for(state="visible", timeout=self.join_timeout_ms)
        await login_field.fill(self.settings.yandex_login)
        await self._shot("login-1-login")
        # Submit by pressing Enter on the field — clicking a generic submit button
        # is unreliable here (the screen also has "Войти по QR-коду" /
        # "Отправить письмо" buttons that would divert to the passwordless flow).
        await login_field.press("Enter")

        # Step 2: password
        passwd_field = page.locator("input[type='password'], input[name='passwd']").first
        await passwd_field.wait_for(state="visible", timeout=self.join_timeout_ms)
        await passwd_field.fill(self.settings.yandex_password)
        await self._shot("login-2-passwd")
        await passwd_field.press("Enter")

        # Step 3: settle — dismiss "bind phone / later" interstitials
        await page.wait_for_timeout(3000)
        for label in ("Не сейчас", "Позже", "Пропустить", "Готово"):
            btn = page.get_by_role("button", name=label, exact=False)
            try:
                if await btn.count() and await btn.first.is_visible():
                    await btn.first.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

        await self._shot("login-3-done")
        # Confirm by loading the profile; a still-unauthenticated session bounces
        # back to an /auth or passwordless (pwl) URL.
        await page.goto(
            "https://passport.yandex.ru/profile",
            wait_until="domcontentloaded",
            timeout=self.join_timeout_ms,
        )
        await page.wait_for_timeout(1500)
        await self._shot("login-4-verify")
        if "/auth" in page.url or "/pwl" in page.url:
            raise RuntimeError(f"Yandex login did not complete (url={page.url})")
        logger.info("Yandex login successful (%s)", page.url)

    async def _reveal_login_field(self, login_field) -> None:
        """Expose the login/password input on the passwordless auth screen."""
        assert self.page is not None
        page = self.page
        try:
            if await login_field.count() and await login_field.first.is_visible():
                return
        except Exception:
            pass
        # Open the "Ещё" menu and pick "Войти по логину".
        more = page.get_by_text("Ещё", exact=False)
        try:
            if await more.count() and await more.first.is_visible():
                await more.first.click()
                await page.wait_for_timeout(1500)
                await self._shot("login-0-more")
        except Exception:
            pass
        for label in ("Войти по логину", "Войти по почте", "по логину"):
            opt = page.get_by_text(label, exact=False)
            try:
                if await opt.count() and await opt.first.is_visible():
                    await opt.first.click()
                    await page.wait_for_timeout(1500)
                    return
            except Exception:
                pass

    async def _submit_passport(self) -> None:
        assert self.page is not None
        page = self.page
        # The passport submit button varies; try id, then role, then Enter.
        for selector in ("button#passp\\:sign-in", "button[type='submit']"):
            btn = page.locator(selector)
            try:
                if await btn.count() and await btn.first.is_visible():
                    await btn.first.click()
                    return
            except Exception:
                pass
        for label in ("Войти", "Продолжить", "Далее"):
            btn = page.get_by_role("button", name=label, exact=False)
            try:
                if await btn.count() and await btn.first.is_visible():
                    await btn.first.click()
                    return
            except Exception:
                pass
        await page.keyboard.press("Enter")

    # ── Telemost join ──────────────────────────────────────────────────────

    async def join(self, url: str) -> None:
        await self.ensure_logged_in()
        assert self.page is not None
        page = self.page

        await page.goto(url, wait_until="domcontentloaded", timeout=self.join_timeout_ms)

        continue_button = page.get_by_role("button", name="Продолжить в браузере")
        if await continue_button.count() and await continue_button.first.is_visible():
            await continue_button.first.click()

        await self._dismiss_known_dialogs()

        # When authenticated the name is taken from the account, so the textbox
        # may be absent — fill it only if it shows up quickly.
        try:
            name_input = page.get_by_role("textbox").first
            await name_input.wait_for(state="visible", timeout=8000)
            await name_input.fill(self.participant_name)
        except PWTimeout:
            logger.info("No name textbox (authenticated join) — using account name")

        await self._ensure_muted()
        await self._shot("join-prejoin")

        connect_button = page.get_by_role("button", name="Подключиться", exact=True)
        await connect_button.wait_for(state="visible", timeout=self.join_timeout_ms)
        await connect_button.click()
        try:
            await connect_button.wait_for(state="hidden", timeout=self.join_timeout_ms)
        except PWTimeout:
            pass
        await self._shot("join-after-connect")
        logger.info("Joined Telemost as %s", self.settings.yandex_login or self.participant_name)

    async def _dismiss_known_dialogs(self) -> None:
        assert self.page is not None
        for _ in range(3):
            button = self.page.get_by_role("button", name="Понятно", exact=True)
            if await button.count() == 0:
                return
            try:
                await button.first.click()
            except Exception:
                return

    async def _ensure_muted(self) -> None:
        assert self.page is not None
        for enabled_name in ("Выключить микрофон", "Выключить камеру"):
            button = self.page.get_by_role("button", name=enabled_name, exact=True)
            try:
                if await button.count():
                    await button.first.click()
            except Exception:
                pass

    async def meeting_ended(self) -> bool:
        if self.page is None or self.page.is_closed():
            return True
        for text in ("Встреча завершена", "Организатор завершил встречу"):
            try:
                if await self.page.get_by_text(text, exact=False).count():
                    return True
            except Exception:
                return True
        return False

    async def close(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
