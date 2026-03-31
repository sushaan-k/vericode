"""Content-addressed verification cache.

Caches successful ``VerificationOutput`` results keyed by a hash of the
full verification identity: spec, backend, provider, target language,
and any user-supplied implementation under proof.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from vericode.artifacts import canonical_spec, sha256_hex
from vericode.spec import Spec

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "vericode"


@dataclass
class CacheEntry:
    """A single cached verification result.

    Attributes:
        cache_key: The content-addressed hash key.
        code: Verified implementation source code.
        proof: Verified proof source code.
        backend: Backend used for verification.
        language: Target language of the implementation.
        certificate_json: JSON string of the proof certificate.
    """

    cache_key: str
    code: str
    proof: str
    backend: str
    language: str
    certificate_json: str
    metadata: dict[str, str] = field(default_factory=dict)


def cache_key(
    spec: Spec,
    backend: str,
    provider: str,
    *,
    language: str,
    existing_code: str | None = None,
    temperature: float,
    max_tokens: int,
) -> str:
    """Compute a content-addressed cache key.

    The key is a SHA-256 hex digest derived from the canonical spec
    representation plus every input that can change the resulting proof
    artifact.

    Args:
        spec: The specification being verified.
        backend: Name of the verification backend.
        provider: Name of the LLM provider.
        language: Target implementation language.
        existing_code: Optional user-supplied implementation being proved.
        temperature: Generation sampling temperature.
        max_tokens: Generation token budget.

    Returns:
        A 64-character hex digest string.
    """
    canonical = canonical_spec(spec)
    code_hash = sha256_hex(existing_code or "")
    combined = (
        f"{canonical}|{backend.lower()}|{provider.lower()}|"
        f"{language.lower()}|{code_hash}|{temperature:.6f}|{max_tokens}"
    )
    return sha256_hex(combined)


class VerificationCache:
    """File-backed content-addressed cache for verification results.

    Each entry is stored as a JSON file named ``<key>.json`` under
    the cache directory.

    Args:
        cache_dir: Directory for cache files.  Created on first write.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR

    @property
    def cache_dir(self) -> Path:
        """Return the cache directory path."""
        return self._cache_dir

    def get(self, key: str) -> CacheEntry | None:
        """Look up a cached entry by key.

        Args:
            key: The content-addressed cache key.

        Returns:
            A ``CacheEntry`` if found, otherwise ``None``.
        """
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            logger.debug("Cache miss", extra={"key": key[:12]})
            return None

        try:
            data = json.loads(path.read_text())
            logger.info("Cache hit", extra={"key": key[:12]})
            return CacheEntry(
                cache_key=data["cache_key"],
                code=data["code"],
                proof=data["proof"],
                backend=data["backend"],
                language=data["language"],
                certificate_json=data["certificate_json"],
                metadata=data.get("metadata", {}),
            )
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.warning("Corrupt cache entry, ignoring", extra={"error": str(exc)})
            return None

    def put(self, entry: CacheEntry) -> None:
        """Write a cache entry to disk.

        Args:
            entry: The cache entry to persist.
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / f"{entry.cache_key}.json"
        data = {
            "cache_key": entry.cache_key,
            "code": entry.code,
            "proof": entry.proof,
            "backend": entry.backend,
            "language": entry.language,
            "certificate_json": entry.certificate_json,
            "metadata": entry.metadata,
        }
        path.write_text(json.dumps(data, indent=2))
        logger.info("Cached verification result", extra={"key": entry.cache_key[:12]})

    def clear(self) -> int:
        """Remove all cache entries.

        Returns:
            The number of entries removed.
        """
        if not self._cache_dir.exists():
            return 0
        removed = 0
        for path in self._cache_dir.glob("*.json"):
            path.unlink()
            removed += 1
        logger.info("Cleared cache", extra={"removed": removed})
        return removed
