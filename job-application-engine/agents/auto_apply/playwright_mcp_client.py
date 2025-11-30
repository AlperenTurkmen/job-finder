"""Deprecated compatibility shim for the removed BrowserMCP client."""

from __future__ import annotations

from .playwright_client import PlaywrightSession as PlaywrightMCPClient
from .playwright_client import PlaywrightClientError as PlaywrightMCPError

__all__ = ["PlaywrightMCPClient", "PlaywrightMCPError"]


def __getattr__(name: str):  # pragma: no cover - defensive import guard
    raise RuntimeError(
        "PlaywrightMCPClient has been removed. Please import PlaywrightSession from auto_apply.playwright_client."
    )
