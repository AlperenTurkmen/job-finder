"""Lightweight async Playwright controller for the auto-apply workflow."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import (  # type: ignore[import]
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)


class PlaywrightClientError(RuntimeError):
    """Raised when a Playwright browser interaction fails."""


@dataclass(slots=True)
class PlaywrightSessionConfig:
    headless: bool = True
    browser: str = "chromium"
    navigation_timeout_ms: int = 90_000
    action_timeout_ms: int = 20_000
    slow_mo: Optional[int] = None


class PlaywrightSession:
    """Context manager that owns a Playwright browser + page."""

    def __init__(self, config: PlaywrightSessionConfig | None = None) -> None:
        self.config = config or PlaywrightSessionConfig()
        self._playwright = None
        self._browser = None
        self._context = None
        self.page = None

    async def __aenter__(self) -> "PlaywrightSession":
        self._playwright = await async_playwright().start()
        browser_factory = getattr(self._playwright, self.config.browser)
        self._browser = await browser_factory.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
        )
        self._context = await self._browser.new_context()
        self.page = await self._context.new_page()
        self.page.set_default_navigation_timeout(self.config.navigation_timeout_ms)
        self.page.set_default_timeout(self.config.action_timeout_ms)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - cleanup path
        await self._close()

    async def goto(self, url: str, wait_until: str = "networkidle") -> None:
        await self._ensure_page()
        try:
            await self.page.goto(url, wait_until=wait_until)
        except (PlaywrightTimeoutError, PlaywrightError) as exc:  # pragma: no cover - network dependent
            raise PlaywrightClientError(f"Navigation failed for {url}: {exc}") from exc

    async def get_dom(self) -> str:
        await self._ensure_page()
        try:
            return await self.page.content()
        except PlaywrightError as exc:  # pragma: no cover - network dependent
            raise PlaywrightClientError(f"Unable to read DOM: {exc}") from exc

    async def click(self, selector: str | None = None, text: str | None = None) -> None:
        await self._ensure_page()
        if not selector and not text:
            raise ValueError("Provide selector or text to click")
        try:
            if selector:
                await self.page.click(selector)
                return
            assert text is not None
            # Try button role first; fall back to text locator.
            locator = self.page.get_by_role("button", name=text, exact=False)
            if await locator.count() > 0:
                await locator.first.click()
                return
            await self.page.get_by_text(text, exact=False).first.click()
        except PlaywrightError as exc:  # pragma: no cover - runtime interaction
            raise PlaywrightClientError(f"Click failed for selector={selector} text={text}: {exc}") from exc

    async def fill(self, selector: str, value: str) -> None:
        await self._ensure_page()
        try:
            await self.page.fill(selector, value)
        except PlaywrightError as exc:  # pragma: no cover - runtime interaction
            raise PlaywrightClientError(f"Fill failed for {selector}: {exc}") from exc

    async def set_checkbox(self, selector: str, checked: bool) -> None:
        await self._ensure_page()
        try:
            if checked:
                await self.page.check(selector)
            else:
                await self.page.uncheck(selector)
        except PlaywrightError as exc:  # pragma: no cover - runtime interaction
            raise PlaywrightClientError(f"Checkbox toggle failed for {selector}: {exc}") from exc

    async def select_option(self, selector: str, *, value: str | None = None, label: str | None = None) -> None:
        await self._ensure_page()
        if not value and not label:
            raise ValueError("Provide value or label to select option")
        try:
            await self.page.select_option(selector, value=value, label=label)
        except PlaywrightError as exc:  # pragma: no cover - runtime interaction
            raise PlaywrightClientError(f"Select option failed for {selector}: {exc}") from exc

    async def select_combobox(
        self,
        selector: str,
        option_text: str,
        *,
        listbox_selector: Optional[str] = None,
    ) -> None:
        await self._ensure_page()
        normalized = option_text.strip()
        if not normalized:
            raise ValueError("option_text must be non-empty")
        try:
            locator = self.page.locator(selector)
            await locator.click()
            await self.page.wait_for_timeout(150)
            target_selector = listbox_selector
            if not target_selector:
                aria_controls = await locator.get_attribute("aria-controls")
                if not aria_controls:
                    aria_controls = await locator.get_attribute("aria-owns")
                if aria_controls:
                    target_selector = aria_controls if aria_controls.startswith("#") else f"#{aria_controls}"
            if target_selector:
                listbox_locator = self.page.locator(target_selector)
            else:
                listbox_locator = self.page.locator("[role='listbox']").last
            await listbox_locator.wait_for(state="visible", timeout=self.config.action_timeout_ms)
            option_locator = listbox_locator.get_by_role("option", name=normalized, exact=False)
            if await option_locator.count() == 0:
                await self.page.keyboard.type(normalized)
                await self.page.wait_for_timeout(150)
                option_locator = listbox_locator.get_by_role("option", name=normalized, exact=False)
            if await option_locator.count() == 0:
                option_locator = listbox_locator.get_by_text(normalized, exact=False)
            if await option_locator.count() == 0:
                raise PlaywrightClientError(
                    f"Combobox option '{option_text}' not found for selector {selector}"
                )
            await option_locator.first.click()
            try:
                await listbox_locator.wait_for(state="hidden", timeout=2000)
            except PlaywrightError:
                pass
        except PlaywrightError as exc:
            raise PlaywrightClientError(
                f"Combobox selection failed for {selector} with option '{option_text}': {exc}"
            ) from exc

    async def wait_for_selector(self, selector: str, timeout: Optional[float] = None) -> None:
        await self._ensure_page()
        ms = int((timeout or (self.config.action_timeout_ms / 1000)) * 1000)
        try:
            await self.page.wait_for_selector(selector, timeout=ms)
        except PlaywrightTimeoutError as exc:
            raise PlaywrightClientError(f"Timeout waiting for selector {selector}") from exc

    async def upload_file(self, selector: str, file_path: str) -> None:
        await self._ensure_page()
        try:
            await self.page.set_input_files(selector, file_path)
        except PlaywrightError as exc:  # pragma: no cover - runtime interaction
            raise PlaywrightClientError(f"File upload failed for {selector}: {exc}") from exc

    async def _ensure_page(self) -> None:
        if not self.page:
            raise PlaywrightClientError("Playwright session is not initialized.")

    async def _close(self) -> None:
        if self.page:
            await self.page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


async def launch_session(headless: bool = True) -> PlaywrightSession:
    session = PlaywrightSession(PlaywrightSessionConfig(headless=headless))
    await session.__aenter__()
    return session


def run_sync(coro):  # pragma: no cover - convenience helper for sync paths
    return asyncio.get_event_loop().run_until_complete(coro)
