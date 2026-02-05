"""
Data store for ingested transaction data with multi-user support
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Multi-user storage for ingested context data
# Structure: {user_id: {transactions, vectorstore, langchain_docs, last_updated}}
user_data_store: Dict[str, Dict[str, Any]] = {}

# Legacy single-user storage (for backward compatibility)
ingested_data_store: Dict[str, Any] = {
    "transactions": [],
    "vectorstore": None,
    "langchain_docs": [],
    "last_updated": None
}


def get_ingested_data(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Get the ingested data store for a specific user or global"""
    if user_id:
        data = user_data_store.get(user_id, {
            "transactions": [],
            "vectorstore": None,
            "langchain_docs": [],
            "last_updated": None
        })
        logger.info(f"📥 MULTI-USER: Retrieved data for user_id='{user_id}' - {len(data.get('transactions', []))} transactions")
        return data
    logger.info(f"📥 LEGACY: Retrieved global data - {len(ingested_data_store.get('transactions', []))} transactions")
    return ingested_data_store


def set_ingested_data(transactions: List[Dict], vectorstore, langchain_docs: List, user_id: Optional[str] = None):
    """Set the ingested data for a specific user or globally"""
    data = {
        "transactions": transactions,
        "vectorstore": vectorstore,
        "langchain_docs": langchain_docs,
        "last_updated": datetime.now().isoformat()
    }

    if user_id:
        global user_data_store
        user_data_store[user_id] = data
        logger.info(f"✅ MULTI-USER: Stored {len(transactions)} transactions for user_id='{user_id}'")
        logger.info(f"✅ MULTI-USER: Total users in store: {len(user_data_store)} - Users: {list(user_data_store.keys())}")
    else:
        global ingested_data_store
        ingested_data_store.update(data)
        logger.info(f"✅ LEGACY: Stored {len(transactions)} transactions in global store")


def clear_ingested_data(user_id: Optional[str] = None):
    """Clear the ingested data for a specific user or globally"""
    if user_id:
        global user_data_store
        if user_id in user_data_store:
            del user_data_store[user_id]
    else:
        global ingested_data_store
        ingested_data_store["transactions"] = []
        ingested_data_store["vectorstore"] = None
        ingested_data_store["langchain_docs"] = []
        ingested_data_store["last_updated"] = None


def has_ingested_data(user_id: Optional[str] = None) -> bool:
    """Check if data has been ingested for a specific user or globally"""
    if user_id:
        exists = user_id in user_data_store and len(user_data_store[user_id].get("transactions", [])) > 0
        logger.info(f"🔍 MULTI-USER: Checking if user_id='{user_id}' has data: {exists}")
        return exists
    exists = len(ingested_data_store["transactions"]) > 0
    logger.info(f"🔍 LEGACY: Checking if global data exists: {exists}")
    return exists


def get_all_users() -> List[str]:
    """Get list of all users who have ingested data"""
    return list(user_data_store.keys())


def get_user_stats() -> Dict[str, Any]:
    """Get statistics about stored user data"""
    return {
        "total_users": len(user_data_store),
        "users": {
            user_id: {
                "transactions_count": len(data.get("transactions", [])),
                "last_updated": data.get("last_updated")
            }
            for user_id, data in user_data_store.items()
        }
    }


