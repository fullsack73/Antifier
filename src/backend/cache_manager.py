"""
Advanced Multi-Level Caching System for Portfolio Optimization
Implements L1 (Memory), L2 (Redis/Disk), and L3 (Database) caching layers
"""

import time
import hashlib
import pickle
import gzip
import os
import logging
import threading
from functools import wraps
from typing import Any, Optional, Dict
import pandas as pd
import numpy as np
import psutil

# Try to import Redis, fallback gracefully if not available
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

class CacheMetrics:
    """Track cache performance metrics across all levels"""
    
    def __init__(self):
        self.l1_hits = 0
        self.l1_misses = 0
        self.l2_hits = 0
        self.l2_misses = 0
        self.l3_hits = 0
        self.l3_misses = 0
        self.start_time = time.time()
        
    def record_hit(self, level: str):
        setattr(self, f"l{level}_hits", getattr(self, f"l{level}_hits") + 1)
        
    def record_miss(self, level: str):
        setattr(self, f"l{level}_misses", getattr(self, f"l{level}_misses") + 1)
        
    def hit_ratio(self, level: str) -> float:
        hits = getattr(self, f"l{level}_hits")
        misses = getattr(self, f"l{level}_misses")
        total = hits + misses
        return hits / total if total > 0 else 0.0
        
    def overall_hit_ratio(self) -> float:
        total_hits = self.l1_hits + self.l2_hits + self.l3_hits
        total_requests = total_hits + self.l1_misses + self.l2_misses + self.l3_misses
        return total_hits / total_requests if total_requests > 0 else 0.0
        
    def log_performance(self):
        uptime = time.time() - self.start_time
        logger.info(f"Cache Performance (uptime: {uptime:.1f}s):")
        logger.info(f"  L1 Hit Ratio: {self.hit_ratio('1'):.1%} ({self.l1_hits}/{self.l1_hits + self.l1_misses})")
        logger.info(f"  L2 Hit Ratio: {self.hit_ratio('2'):.1%} ({self.l2_hits}/{self.l2_hits + self.l2_misses})")
        logger.info(f"  L3 Hit Ratio: {self.hit_ratio('3'):.1%} ({self.l3_hits}/{self.l3_hits + self.l3_misses})")
        logger.info(f"  Overall Hit Ratio: {self.overall_hit_ratio():.1%}")

class L1MemoryCache:
    """L1 In-Memory Cache with intelligent memory management"""
    
    def __init__(self, max_memory_gb: float = 2.0):  # 기본값 5GB에서 2GB로 축소
        self.max_memory_bytes = int(max_memory_gb * 1024**3)
        self.cache = {}
        self.access_times = {}
        self.cache_lock = threading.RLock()
        self.current_memory_usage = 0
        
        logger.info(f"L1 Cache initialized with {max_memory_gb}GB memory limit")
        
    def _get_cache_key(self, *args, **kwargs) -> str:
        """Generate consistent cache key from arguments"""
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.md5(key_data.encode()).hexdigest()
        
    def _estimate_size(self, obj) -> int:
        """Estimate memory size of object"""
        try:
            return len(pickle.dumps(obj))
        except:
            # Fallback estimation for unpicklable objects
            if isinstance(obj, pd.DataFrame):
                return obj.memory_usage(deep=True).sum()
            elif isinstance(obj, np.ndarray):
                return obj.nbytes
            else:
                return 1024  # Default 1KB estimate
                
    def _cleanup_if_needed(self, required_space: int):
        """Clean up cache if memory pressure detected"""
        current_memory = psutil.virtual_memory().percent
        
        # 더 공격적인 메모리 정리 - 임계값 낮춤
        if current_memory > 75 or self.current_memory_usage + required_space > self.max_memory_bytes:
            self._cleanup_lru(percentage=60)  # 60% 정리
        elif current_memory > 65:
            self._cleanup_lru(percentage=40)  # 40% 정리
            
    def _cleanup_lru(self, percentage: int):
        """Remove least recently used items"""
        with self.cache_lock:
            if not self.cache:
                return
                
            # Sort by access time (oldest first)
            sorted_keys = sorted(self.access_times.items(), key=lambda x: x[1])
            items_to_remove = int(len(sorted_keys) * percentage / 100)
            
            removed_memory = 0
            for key, _ in sorted_keys[:items_to_remove]:
                if key in self.cache:
                    obj_size = self._estimate_size(self.cache[key])
                    del self.cache[key]
                    del self.access_times[key]
                    removed_memory += obj_size
                    
            self.current_memory_usage -= removed_memory
            logger.info(f"L1 Cache cleanup: removed {items_to_remove} items, freed {removed_memory / 1024**2:.1f}MB")
            
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache"""
        with self.cache_lock:
            if key in self.cache:
                self.access_times[key] = time.time()
                return self.cache[key]
            return None
            
    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set item in cache with TTL"""
        obj_size = self._estimate_size(value)
        
        # Check if we need cleanup
        self._cleanup_if_needed(obj_size)
        
        with self.cache_lock:
            # Store with expiration time
            expiry_time = time.time() + ttl
            self.cache[key] = {
                'value': value,
                'expiry': expiry_time,
                'size': obj_size
            }
            self.access_times[key] = time.time()
            self.current_memory_usage += obj_size
            
    def is_expired(self, key: str) -> bool:
        """Check if cache entry is expired"""
        if key not in self.cache:
            return True
        return time.time() > self.cache[key]['expiry']
        
    def get_valid(self, key: str) -> Optional[Any]:
        """Get item only if not expired"""
        if self.is_expired(key):
            if key in self.cache:
                self._remove_key(key)
            return None
        return self.get(key)['value'] if key in self.cache else None
        
    def _remove_key(self, key: str):
        """Remove key and update memory usage"""
        with self.cache_lock:
            if key in self.cache:
                self.current_memory_usage -= self.cache[key]['size']
                del self.cache[key]
                del self.access_times[key]
                
    def clear(self):
        """Clear all cache entries"""
        with self.cache_lock:
            self.cache.clear()
            self.access_times.clear()
            self.current_memory_usage = 0
            
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            'entries': len(self.cache),
            'memory_usage_mb': self.current_memory_usage / 1024**2,
            'memory_limit_mb': self.max_memory_bytes / 1024**2,
            'memory_utilization': self.current_memory_usage / self.max_memory_bytes
        }

class L2PersistentCache:
    """L2 Redis/Disk Cache for persistent storage"""
    
    def __init__(self, cache_dir: str = ".cache", use_redis: bool = True):
        self.cache_dir = cache_dir
        self.use_redis = use_redis and REDIS_AVAILABLE
        self.redis_client = None
        
        # Create cache directory
        os.makedirs(cache_dir, exist_ok=True)
        
        # Try to connect to Redis
        if self.use_redis:
            try:
                self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)
                self.redis_client.ping()  # Test connection
                logger.info("L2 Cache: Connected to Redis")
            except Exception as e:
                logger.warning(f"L2 Cache: Redis connection failed ({e}), falling back to disk")
                self.use_redis = False
                
        if not self.use_redis:
            logger.info(f"L2 Cache: Using disk storage in {cache_dir}")
            
    def _get_disk_path(self, key: str) -> str:
        """Get disk path for cache key"""
        return os.path.join(self.cache_dir, f"{key}.cache")
        
    def get(self, key: str) -> Optional[Any]:
        """Get item from L2 cache"""
        try:
            if self.use_redis and self.redis_client:
                data = self.redis_client.get(key)
                if data:
                    return pickle.loads(gzip.decompress(data))
            else:
                # Disk fallback
                disk_path = self._get_disk_path(key)
                if os.path.exists(disk_path):
                    with open(disk_path, 'rb') as f:
                        return pickle.loads(gzip.decompress(f.read()))
        except Exception as e:
            logger.error(f"L2 Cache get error for key {key}: {e}")
        return None
        
    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set item in L2 cache"""
        try:
            compressed_data = gzip.compress(pickle.dumps(value))
            
            if self.use_redis and self.redis_client:
                self.redis_client.setex(key, ttl, compressed_data)
            else:
                # Disk fallback with TTL file
                disk_path = self._get_disk_path(key)
                with open(disk_path, 'wb') as f:
                    f.write(compressed_data)
                # Store expiry time in separate file
                with open(disk_path + '.ttl', 'w') as f:
                    f.write(str(time.time() + ttl))
                    
        except Exception as e:
            logger.error(f"L2 Cache set error for key {key}: {e}")
            
    def is_expired(self, key: str) -> bool:
        """Check if L2 cache entry is expired"""
        try:
            if self.use_redis and self.redis_client:
                return self.redis_client.ttl(key) <= 0
            else:
                ttl_path = self._get_disk_path(key) + '.ttl'
                if os.path.exists(ttl_path):
                    with open(ttl_path, 'r') as f:
                        expiry_time = float(f.read().strip())
                        return time.time() > expiry_time
        except Exception as e:
            logger.error(f"L2 Cache expiry check error for key {key}: {e}")
        return True
        
    def clear(self):
        """Clear L2 cache"""
        try:
            if self.use_redis and self.redis_client:
                self.redis_client.flushdb()
            else:
                # Clear disk cache
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith('.cache') or filename.endswith('.ttl'):
                        os.remove(os.path.join(self.cache_dir, filename))
        except Exception as e:
            logger.error(f"L2 Cache clear error: {e}")

class MultiLevelCache:
    """Coordinated multi-level caching system"""
    
    def __init__(self, max_memory_gb: float = 5.0, cache_dir: str = ".cache"):
        self.l1_cache = L1MemoryCache(max_memory_gb)
        self.l2_cache = L2PersistentCache(cache_dir)
        self.metrics = CacheMetrics()
        
        # Start background monitoring
        self._start_monitoring()
        
    def _start_monitoring(self):
        """Start background thread for cache monitoring"""
        def monitor():
            while True:
                time.sleep(300)  # Every 5 minutes
                self.metrics.log_performance()
                
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
        
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache hierarchy (L1 -> L2 -> miss)"""
        # Try L1 first
        value = self.l1_cache.get_valid(key)
        if value is not None:
            self.metrics.record_hit("1")
            return value
            
        self.metrics.record_miss("1")
        
        # Try L2
        if not self.l2_cache.is_expired(key):
            value = self.l2_cache.get(key)
            if value is not None:
                self.metrics.record_hit("2")
                # Promote to L1
                self.l1_cache.set(key, value, ttl=900)  # 15 min TTL in L1
                return value
                
        self.metrics.record_miss("2")
        return None
        
    def set(self, key: str, value: Any, l1_ttl: int = 900, l2_ttl: int = 3600):
        """Set item in both cache levels"""
        self.l1_cache.set(key, value, l1_ttl)
        self.l2_cache.set(key, value, l2_ttl)
        
    def clear(self):
        """Clear all cache levels"""
        self.l1_cache.clear()
        self.l2_cache.clear()
        
    def stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        l1_stats = self.l1_cache.stats()
        return {
            'l1_cache': l1_stats,
            'hit_ratios': {
                'l1': self.metrics.hit_ratio("1"),
                'l2': self.metrics.hit_ratio("2"),
                'overall': self.metrics.overall_hit_ratio()
            },
            'requests': {
                'l1_hits': self.metrics.l1_hits,
                'l1_misses': self.metrics.l1_misses,
                'l2_hits': self.metrics.l2_hits,
                'l2_misses': self.metrics.l2_misses
            }
        }

# Global cache instance
_global_cache = None

def get_cache() -> MultiLevelCache:
    """Get global cache instance (singleton)"""
    global _global_cache
    if _global_cache is None:
        _global_cache = MultiLevelCache()
    return _global_cache

def cached(l1_ttl: int = 900, l2_ttl: int = 3600, key_func=None):
    """Decorator for automatic caching of function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache()
            
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}_{hashlib.md5(str(args + tuple(kwargs.items())).encode()).hexdigest()}"
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"Cache HIT for {func.__name__}")
                return result
                
            # Cache miss - compute result
            logger.debug(f"Cache MISS for {func.__name__}")
            result = func(*args, **kwargs)
            
            # Store in cache
            cache.set(cache_key, result, l1_ttl, l2_ttl)
            return result
            
        return wrapper
    return decorator

# Convenience functions for common cache operations

