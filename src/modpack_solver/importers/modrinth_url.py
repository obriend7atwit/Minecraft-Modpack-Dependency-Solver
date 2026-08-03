"""Parsing and validation for supported Modrinth web URLs."""

from __future__ import annotations

from enum import Enum
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict


class ModrinthResourceKind(str, Enum):
    MOD = "mod"
    MODPACK = "modpack"


class ParsedModrinthUrl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ModrinthResourceKind
    slug: str
    version: str | None = None
    original_url: str


def parse_modrinth_url(url: str) -> ParsedModrinthUrl:
    """Parse a supported mod or modpack URL from ``modrinth.com``."""

    original = url.strip()
    if not original:
        raise ValueError("Modrinth URL cannot be empty.")

    parsed = urlparse(original)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in {"modrinth.com", "www.modrinth.com"}:
        raise ValueError("URL must use http(s) and the modrinth.com host.")

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) not in {2, 4} or parts[0] not in {kind.value for kind in ModrinthResourceKind}:
        raise ValueError(
            "Supported Modrinth paths are /mod/<slug>, /modpack/<slug>, and their /version/<version> forms."
        )
    if len(parts) == 4 and parts[2] != "version":
        raise ValueError("Unsupported Modrinth URL path.")
    if not parts[1] or (len(parts) == 4 and not parts[3]):
        raise ValueError("Modrinth URL is missing a project slug or version.")

    return ParsedModrinthUrl(
        kind=ModrinthResourceKind(parts[0]),
        slug=parts[1],
        version=parts[3] if len(parts) == 4 else None,
        original_url=original,
    )
