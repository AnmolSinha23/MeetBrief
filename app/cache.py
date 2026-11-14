"""Disk cache for Tavily search and LLM calls."""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

class DiskCache:
    """Simple JSON disk cache with TTL support."""

    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def make_key(prefix: str, **kwargs: Any) -> str:
        """Generates a stable sha256 cache key from keyword arguments."""
        # Sort keys for deterministic representation
        serialized = json.dumps(kwargs, sort_keys=True, default=str)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"{prefix}_{digest}"

    def get(self, key: str) -> Optional[dict]:
        """Retrieves cached data if present and not expired."""
        file_path = self.cache_dir / f"{key}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                record = json.load(f)

            expires_at = record.get("expires_at", 0)
            if time.time() > expires_at:
                try:
                    file_path.unlink()
                except OSError:
                    pass
                return None

            return record.get("data")
        except Exception as e:
            logger.warning(f"Error reading cache file {file_path}: {e}")
            return None

    def set(self, key: str, data: Any, ttl_hours: int = 12) -> None:
        """Writes data to cache with given TTL in hours."""
        file_path = self.cache_dir / f"{key}.json"
        record = {
            "created_at": time.time(),
            "expires_at": time.time() + (ttl_hours * 3600),
            "data": data,
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Error writing cache file {file_path}: {e}")

    def clear(self) -> None:
        """Removes all cache entries."""
        for p in self.cache_dir.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass
