"""
Cache management for query results
"""

import hashlib
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)

# Query cache for pagination (stores LLM responses and filtered results)
query_cache: Dict[str, Dict[str, Any]] = {}


def generate_query_id(prompt: str, filters: Dict[str, Any], user_id: str = None) -> str:
    """Generate a unique query ID based on prompt, filters, and user_id"""
    # Include user_id to ensure cache isolation between users
    user_part = f"user_{user_id}_" if user_id else "global_"
    cache_key = f"{user_part}{prompt}_{json.dumps(filters, sort_keys=True)}"
    query_id = hashlib.md5(cache_key.encode()).hexdigest()
    return query_id


def cleanup_expired_cache():
    """Remove expired cache entries"""
    global query_cache
    current_time = datetime.now()
    expired_keys = []

    for query_id, cache_data in query_cache.items():
        if current_time - cache_data["timestamp"] > timedelta(minutes=settings.CACHE_TTL_MINUTES):
            expired_keys.append(query_id)

    for key in expired_keys:
        del query_cache[key]
        logger.info(f"Removed expired cache entry: {key}")


def get_cached_query(query_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached query results if still valid"""
    cleanup_expired_cache()

    if query_id in query_cache:
        cache_data = query_cache[query_id]
        if datetime.now() - cache_data["timestamp"] <= timedelta(minutes=settings.CACHE_TTL_MINUTES):
            logger.info(f"✅ Cache HIT for query_id: {query_id} - {len(cache_data.get('filtered_docs', []))} docs cached")
            return cache_data
        else:
            # Expired, remove it
            del query_cache[query_id]
            logger.info(f"⏰ Cache EXPIRED for query_id: {query_id}")

    logger.info(f"❌ Cache MISS for query_id: {query_id}")
    return None


def cache_query_results(query_id: str, answer: str, mode: str,
                       filtered_docs: List[Dict], filters_applied: Optional[List[str]],
                       statistics: Optional[Dict[str, Any]] = None):
    """Cache query results for pagination"""
    global query_cache

    query_cache[query_id] = {
        "answer": answer,
        "mode": mode,
        "filtered_docs": filtered_docs,
        "filters_applied": filters_applied,
        "statistics": statistics,
        "timestamp": datetime.now()
    }
    logger.info(f"💾 CACHED query results for query_id: {query_id} (mode={mode}, {len(filtered_docs)} transactions, answer_len={len(answer)})")
    logger.info(f"💾 Total cache entries: {len(query_cache)}")
