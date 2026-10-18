"""Structured download failure classification shared by queue and API layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union


class DownloadErrorCode(str, Enum):
    NETWORK = "network"
    RATE_LIMITED = "rate_limited"
    AUTH_REQUIRED = "auth_required"
    GEO_RESTRICTED = "geo_restricted"
    NOT_FOUND = "not_found"
    FFMPEG_MISSING = "ffmpeg_missing"
    INVALID_REQUEST = "invalid_request"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DownloadFailure:
    code: DownloadErrorCode
    message: str
    retryable: bool


def classify_download_error(error: Union[BaseException, str]) -> DownloadFailure:
    """Map heterogeneous yt-dlp/runtime errors into a stable product contract.

    The classifier is deliberately conservative: only failures that are commonly
    transient are marked retryable. Unknown failures require inspection rather than
    silently entering retry loops.
    """
    message = str(error).strip() or error.__class__.__name__
    text = message.lower()

    if any(token in text for token in (
        "requires ffmpeg", "ffmpeg not found", "ffmpeg is not installed",
        "ffprobe not found",
    )):
        return DownloadFailure(DownloadErrorCode.FFMPEG_MISSING, message, False)

    if any(token in text for token in (
        "429", "too many requests", "rate limit", "rate-limit",
    )):
        return DownloadFailure(DownloadErrorCode.RATE_LIMITED, message, True)

    if any(token in text for token in (
        "sign in", "login required", "authentication required", "confirm you're not a bot",
        "confirm you’re not a bot", "cookies are required", "use --cookies",
    )):
        return DownloadFailure(DownloadErrorCode.AUTH_REQUIRED, message, False)

    if any(token in text for token in (
        "not available in your country", "geo-restricted", "geo restricted",
        "not available from your location",
    )):
        return DownloadFailure(DownloadErrorCode.GEO_RESTRICTED, message, False)

    if any(token in text for token in (
        "video unavailable", "private video", "has been removed", "404 not found",
        "this video is unavailable",
    )):
        return DownloadFailure(DownloadErrorCode.NOT_FOUND, message, False)

    if any(token in text for token in (
        "unsupported url", "invalid url", "malformed url", "url must",
    )):
        return DownloadFailure(DownloadErrorCode.INVALID_REQUEST, message, False)

    if any(token in text for token in (
        "timed out", "timeout", "connection reset", "connection refused",
        "temporary failure", "temporarily unavailable", "network is unreachable",
        "remote end closed", "http error 500", "http error 502",
        "http error 503", "http error 504",
    )):
        return DownloadFailure(DownloadErrorCode.NETWORK, message, True)

    return DownloadFailure(DownloadErrorCode.UNKNOWN, message, False)
