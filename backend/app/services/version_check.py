import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx

from app.http_identity import merge_outbound_headers

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_WEB_BASE_URL = "https://github.com"
HEYM_GITHUB_REPO = "heymrun/heym"
RELEASE_CHECK_CACHE_SECONDS = 3600
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_VERSION_NUMBER_RE = re.compile(r"^v?(\d+(?:\.\d+){0,3})", re.IGNORECASE)


@dataclass(frozen=True)
class GithubRelease:
    tag_name: str
    release_url: str
    published_at: str | None = None


@dataclass(frozen=True)
class VersionStatus:
    current_version: str
    latest_version: str | None
    update_available: bool
    release_url: str | None
    compare_url: str | None
    compare_label: str | None
    source: str
    checked_at: datetime | None
    error: str | None = None


_cached_status: VersionStatus | None = None
_cached_key: tuple[str, str] | None = None
_cached_until: datetime | None = None
_cache_lock = asyncio.Lock()


def clear_version_status_cache() -> None:
    """Clear cached GitHub version status."""
    global _cached_key, _cached_status, _cached_until

    _cached_status = None
    _cached_key = None
    _cached_until = None


def is_version_behind(current_version: str, latest_version: str) -> bool:
    """Return True when current_version is older than latest_version."""
    current_parts = _version_parts(current_version)
    latest_parts = _version_parts(latest_version)
    if current_parts is None or latest_parts is None:
        return False
    return current_parts < latest_parts


async def get_version_status(current_version: str, force_refresh: bool = False) -> VersionStatus:
    """Fetch and cache version status against the Heym GitHub release."""
    now = datetime.now(UTC)
    cache_key = (current_version, HEYM_GITHUB_REPO)

    cached = _get_cached_status(cache_key, now, force_refresh)
    if cached is not None:
        return cached

    async with _cache_lock:
        cached = _get_cached_status(cache_key, now, force_refresh)
        if cached is not None:
            return cached

        status = await _load_version_status(current_version, HEYM_GITHUB_REPO, now)
        _set_cached_status(cache_key, status, now)
        return status


async def _load_version_status(current_version: str, repo: str, now: datetime) -> VersionStatus:
    try:
        normalized_repo = _normalize_repo(repo)
        release = await _fetch_latest_release(normalized_repo)
        return _build_version_status(current_version, normalized_repo, release, now)
    except Exception as exc:
        return VersionStatus(
            current_version=current_version,
            latest_version=None,
            update_available=False,
            release_url=None,
            compare_url=None,
            compare_label=None,
            source="github",
            checked_at=now,
            error=str(exc),
        )


def _build_version_status(
    current_version: str,
    repo: str,
    release: GithubRelease,
    checked_at: datetime,
) -> VersionStatus:
    latest_version = _version_label(release.tag_name)
    current_label = _version_label(current_version)
    update_available = is_version_behind(current_label, latest_version)
    compare_label = f"{current_label}..{latest_version}" if update_available else None
    compare_url = (
        _build_compare_url(repo, current_version, release.tag_name) if update_available else None
    )

    return VersionStatus(
        current_version=current_label,
        latest_version=latest_version,
        update_available=update_available,
        release_url=release.release_url,
        compare_url=compare_url,
        compare_label=compare_label,
        source="github",
        checked_at=checked_at,
        error=None,
    )


async def _fetch_latest_release(repo: str) -> GithubRelease:
    headers = merge_outbound_headers(
        {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    timeout = httpx.Timeout(5.0)
    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        response = await client.get(f"{GITHUB_API_BASE_URL}/repos/{repo}/releases/latest")
        response.raise_for_status()
        data = response.json()

    tag_name = str(data.get("tag_name") or "").strip()
    if not tag_name:
        raise ValueError("GitHub latest release has no tag_name")

    release_url = str(data.get("html_url") or "").strip()
    if not release_url:
        release_url = f"{GITHUB_WEB_BASE_URL}/{repo}/releases/tag/{quote(tag_name, safe='')}"

    published_at = data.get("published_at")
    return GithubRelease(
        tag_name=tag_name,
        release_url=release_url,
        published_at=str(published_at) if published_at else None,
    )


def _normalize_repo(repo: str) -> str:
    normalized = repo.strip()
    if not _REPO_RE.match(normalized):
        raise ValueError("GitHub repo must be in owner/repo format")
    return normalized


def _build_compare_url(repo: str, current_version: str, latest_tag: str) -> str:
    current_tag = _current_tag_for_compare(current_version, latest_tag)
    return (
        f"{GITHUB_WEB_BASE_URL}/{repo}/compare/"
        f"{quote(current_tag, safe='')}...{quote(latest_tag, safe='')}"
    )


def _current_tag_for_compare(current_version: str, latest_tag: str) -> str:
    current = current_version.strip()
    if latest_tag.lower().startswith("v") and not current.lower().startswith("v"):
        return f"v{current}"
    return current


def _version_label(version: str) -> str:
    normalized = version.strip()
    if normalized.lower().startswith("v"):
        normalized = normalized[1:]
    return normalized


def _version_parts(version: str) -> tuple[int, ...] | None:
    match = _VERSION_NUMBER_RE.match(version.strip())
    if match is None:
        return None

    parts = [int(part) for part in match.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _get_cached_status(
    cache_key: tuple[str, str],
    now: datetime,
    force_refresh: bool,
) -> VersionStatus | None:
    if force_refresh:
        return None
    if _cached_key != cache_key or _cached_until is None or _cached_status is None:
        return None
    if now >= _cached_until:
        return None
    return _cached_status


def _set_cached_status(
    cache_key: tuple[str, str],
    status: VersionStatus,
    now: datetime,
) -> None:
    global _cached_key, _cached_status, _cached_until

    _cached_status = status
    _cached_key = cache_key
    _cached_until = now + timedelta(seconds=RELEASE_CHECK_CACHE_SECONDS)
