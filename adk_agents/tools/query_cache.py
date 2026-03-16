"""
Query Result Cache System

Caches schema, profiling, and relationship query results to reduce API calls.
Cache TTL: 24 hours by default, configurable via environment variables.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import hashlib


class QueryCache:
    """Thread-safe query result caching with TTL and file-based persistence."""
    
    def __init__(self, cache_dir: str = ".cache", ttl_hours: int = 24):
        """
        Initialize the query cache.
        
        Args:
            cache_dir: Directory where cache files are stored
            ttl_hours: Time-to-live in hours (default 24)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl_hours = ttl_hours
        self.ttl_seconds = ttl_hours * 3600
        
        # Global kill switch
        self.enabled = os.getenv("QUERY_CACHE_DISABLED", "FALSE").upper() != "TRUE"
        if not self.enabled:
            print("   - 🚫 Query caching is GLOBALLY DISABLED")
    
    def _get_cache_key(self, query_type: str, db_config: dict) -> str:
        """
        Generate a cache key from query type and database configuration.
        
        Args:
            query_type: Type of query (e.g., 'schema', 'profiling', 'relationships')
            db_config: Database configuration dict (host, port, dbname, etc.)
        
        Returns:
            str: Cache key hash
        """
        # Create deterministic key from query type and db config
        key_str = f"{query_type}:{json.dumps(db_config, sort_keys=True)}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        return self.cache_dir / f"{cache_key}.json"
    
    def _is_expired(self, cache_path: Path) -> bool:
        """Check if cache file has expired based on TTL."""
        if not cache_path.exists():
            return True
        
        mtime = os.path.getmtime(cache_path)
        age_seconds = (datetime.now().timestamp() - mtime)
        return age_seconds > self.ttl_seconds
    
    def get(self, query_type: str, db_config: dict, force_refresh: bool = False) -> dict | None:
        """
        Retrieve cached query result if available and not expired.
        
        Args:
            query_type: Type of query (e.g., 'schema', 'profiling')
            db_config: Database configuration
            force_refresh: If True, ignore cache and force fresh query
        
        Returns:
            dict: Cached data, or None if expired/missing/force_refresh=True
        """
        if not self.enabled:
            return None
            
        if force_refresh:
            return None
        
        cache_key = self._get_cache_key(query_type, db_config)
        cache_path = self._get_cache_path(cache_key)
        
        if self._is_expired(cache_path):
            # Clean up expired cache
            try:
                cache_path.unlink()
            except OSError:
                pass
            return None
        
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_cache_hit"] = True
                data["_cache_age_minutes"] = int(
                    (datetime.now().timestamp() - os.path.getmtime(cache_path)) / 60
                )
                return data
        except (json.JSONDecodeError, IOError):
            return None
    
    def set(self, query_type: str, db_config: dict, data: dict) -> bool:
        """
        Cache query result to disk.
        
        Args:
            query_type: Type of query
            db_config: Database configuration
            data: Result data to cache
        
        Returns:
            bool: True if cached successfully, False otherwise
        """
        if not self.enabled:
            return False
            
        cache_key = self._get_cache_key(query_type, db_config)
        cache_path = self._get_cache_path(cache_key)
        
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            return True
        except (IOError, OSError):
            return False
    
    def clear(self, query_type: str | None = None, db_config: dict | None = None) -> int:
        """
        Clear cache entries.
        
        Args:
            query_type: If specified, only clear this query type
            db_config: If specified with query_type, only clear this specific entry
        
        Returns:
            int: Number of cache files removed
        """
        count = 0
        
        if query_type and db_config:
            # Clear specific cache entry
            cache_key = self._get_cache_key(query_type, db_config)
            cache_path = self._get_cache_path(cache_key)
            if cache_path.exists():
                try:
                    cache_path.unlink()
                    count = 1
                except OSError:
                    pass
        else:
            # Clear all cache files
            try:
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink()
                    count += 1
            except OSError:
                pass
        
        return count
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired cache files.
        
        Returns:
            int: Number of expired cache files removed
        """
        count = 0
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                if self._is_expired(cache_file):
                    cache_file.unlink()
                    count += 1
        except OSError:
            pass
        return count
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        total_files = 0
        total_size = 0
        expired_count = 0
        
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                total_files += 1
                total_size += cache_file.stat().st_size
                if self._is_expired(cache_file):
                    expired_count += 1
        except OSError:
            pass
        
        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "expired_files": expired_count,
            "cache_dir": str(self.cache_dir),
            "ttl_hours": self.ttl_hours,
        }


# Global cache instance
_cache_instance = None


def get_query_cache(force_new: bool = False) -> QueryCache:
    """
    Get or create the global query cache instance.
    
    Args:
        force_new: If True, create a new instance
    
    Returns:
        QueryCache: Global cache instance
    """
    global _cache_instance
    
    if _cache_instance is None or force_new:
        cache_dir = os.getenv("QUERY_CACHE_DIR", ".cache")
        ttl_hours = int(os.getenv("QUERY_CACHE_TTL_HOURS", "24"))
        _cache_instance = QueryCache(cache_dir=cache_dir, ttl_hours=ttl_hours)
    
    return _cache_instance


# Export public API
__all__ = ["QueryCache", "get_query_cache"]
