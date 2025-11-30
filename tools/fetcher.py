"""HTTP fetching utilities for downloading job pages."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import requests

DEFAULT_TIMEOUT = 20
DEFAULT_BACKOFF = 1.5


class FetchError(RuntimeError):
	"""Raised when repeated attempts to fetch a URL fail."""


def fetch_html(
	url: str,
	*,
	timeout: int = DEFAULT_TIMEOUT,
	max_attempts: int = 3,
	backoff: float = DEFAULT_BACKOFF,
	session: Optional[requests.Session] = None,
) -> str:
	"""Download the HTML body for the given URL with simple retries."""

	attempt = 0
	exc: Exception | None = None
	while attempt < max_attempts:
		attempt += 1
		try:
			client = session or requests
			response = client.get(url, timeout=timeout)
			response.raise_for_status()
			return response.text
		except (requests.RequestException, OSError) as error:  # network errors
			exc = error
			if attempt >= max_attempts:
				break
			sleep_duration = backoff ** (attempt - 1)
			time.sleep(sleep_duration)
	raise FetchError(f"Failed to fetch {url!r} after {max_attempts} attempts") from exc


def fetch_html_to_file(
	url: str,
	destination: Path | str,
	*,
	timeout: int = DEFAULT_TIMEOUT,
	max_attempts: int = 3,
	backoff: float = DEFAULT_BACKOFF,
) -> str:
	"""Fetch the HTML for URL and save it to destination path."""

	html = fetch_html(url, timeout=timeout, max_attempts=max_attempts, backoff=backoff)
	path = Path(destination)
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(html, encoding="utf-8")
	return html
