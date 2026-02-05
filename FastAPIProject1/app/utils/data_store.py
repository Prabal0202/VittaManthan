"""
Data store for ingested transaction data with PostgreSQL persistence and multi-user support
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
import pickle
import base64

# Import database models
try:
    from app.db.database import SessionLocal, UserData
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ Database not available - using in-memory storage only")

logger = logging.getLogger(__name__)

# In-memory cache for faster access (acts as L1 cache)
_memory_cache: Dict[str, Dict[str, Any]] = {}

# Legacy single-user storage (for backward compatibility)
_legacy_store: Dict[str, Any] = {
    "transactions": [],
    "vectorstore": None,
    "langchain_docs": [],
    "last_updated": None
}


def _serialize_vectorstore(vectorstore) -> str:
    """Serialize FAISS vectorstore to base64 string for database storage"""
    try:
        vectorstore_bytes = pickle.dumps(vectorstore)
        return base64.b64encode(vectorstore_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"❌ Vectorstore serialization failed: {e}")
        raise


def _deserialize_vectorstore(data: str):
    """Deserialize base64 string back to FAISS vectorstore"""
    try:
        vectorstore_bytes = base64.b64decode(data.encode('utf-8'))
        return pickle.loads(vectorstore_bytes)
    except Exception as e:
        logger.error(f"❌ Vectorstore deserialization failed: {e}")
        raise


def set_ingested_data(transactions: List[Dict], vectorstore, langchain_docs: List, user_id: Optional[str] = None):
    """
    Store ingested data with PostgreSQL persistence and memory caching

    Args:
        transactions: List of transaction dictionaries
        vectorstore: FAISS vectorstore instance
        langchain_docs: List of LangChain documents
        user_id: Optional user identifier (None for global/legacy storage)
    """
    storage_key = user_id if user_id else "global"

    # Prepare data structure
    data = {
        "transactions": transactions,
        "vectorstore": vectorstore,
        "langchain_docs": langchain_docs,
        "last_updated": datetime.now().isoformat()
    }

    # ALWAYS update memory cache FIRST (immediate, fast)
    if user_id:
        _memory_cache[storage_key] = data
        logger.info(f"✅ MULTI-USER: Cached {len(transactions)} transactions for user_id='{user_id}'")
        logger.info(f"✅ MULTI-USER: Total users in cache: {len(_memory_cache)} - Users: {list(_memory_cache.keys())}")
    else:
        global _legacy_store
        _legacy_store.update(data)
        logger.info(f"✅ LEGACY: Stored {len(transactions)} transactions in global store")

    # Save ONLY transactions to database (not vectorstore - too large!)
    # Vectorstore will be rebuilt from transactions when needed
    if DB_AVAILABLE and user_id:
        import threading

        def save_to_db():
            """Background thread to save to database"""
            db = SessionLocal()
            try:
                # Check if user data exists
                user_data = db.query(UserData).filter_by(user_id=storage_key).first()

                if user_data:
                    # Update existing record - only transactions
                    user_data.transactions = transactions
                    user_data.vectorstore_data = ""  # Empty - will rebuild on load
                    user_data.last_updated = datetime.utcnow()
                    logger.info(f"📝 UPDATED {len(transactions)} transactions in PostgreSQL for '{storage_key}'")
                else:
                    # Create new record
                    user_data = UserData(
                        user_id=storage_key,
                        transactions=transactions,
                        vectorstore_data=""  # Empty - will rebuild on load
                    )
                    db.add(user_data)
                    logger.info(f"✨ CREATED new record in PostgreSQL for '{storage_key}'")

                db.commit()
                logger.info(f"💾 PERSISTENT: Saved {len(transactions)} transactions for '{storage_key}' to PostgreSQL (vectorstore will rebuild on load)")

            except Exception as e:
                db.rollback()
                logger.error(f"❌ Background database save failed for '{storage_key}': {e}")
            finally:
                db.close()

        # Start background thread (non-blocking)
        thread = threading.Thread(target=save_to_db, daemon=True)
        thread.start()
        logger.info(f"⚡ Started background save to PostgreSQL for '{storage_key}'")


def get_ingested_data(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve ingested data from cache or PostgreSQL

    Args:
        user_id: Optional user identifier (None for global/legacy storage)

    Returns:
        Dictionary with transactions, vectorstore, langchain_docs, and metadata
    """
    storage_key = user_id if user_id else "global"

    # Check memory cache first (L1 cache)
    if user_id and storage_key in _memory_cache:
        logger.info(f"📦 CACHE HIT: Retrieved data for '{storage_key}' from memory")
        return _memory_cache[storage_key]

    if not user_id:
        logger.info(f"📥 LEGACY: Retrieved global data - {len(_legacy_store.get('transactions', []))} transactions")
        return _legacy_store

    # Load from database (L2 cache) and rebuild vectorstore
    if DB_AVAILABLE and user_id:
        db = SessionLocal()
        try:
            user_data = db.query(UserData).filter_by(user_id=storage_key).first()

            if user_data:
                transactions = user_data.transactions

                # Rebuild vectorstore from transactions
                logger.info(f"🔄 Rebuilding vectorstore for '{storage_key}' from {len(transactions)} transactions...")

                # Import here to avoid circular dependency
                from app.services.embeddings import HuggingFaceEmbeddings
                from app.services.rag_service import RAGService
                from app.core.config import settings

                try:
                    # Get embeddings model (should be already initialized)
                    embeddings_model = HuggingFaceEmbeddings(settings.EMBEDDING_MODEL)

                    # Create RAG service and rebuild vectorstore
                    from app.services.llm import initialize_llm
                    llm = initialize_llm(streaming=False)
                    rag_service = RAGService(embeddings_model, llm)

                    vectorstore, langchain_docs = rag_service.create_vector_store(transactions)
                    logger.info(f"✅ Vectorstore rebuilt successfully for '{storage_key}'")

                except Exception as e:
                    logger.error(f"❌ Failed to rebuild vectorstore for '{storage_key}': {e}")
                    vectorstore = None
                    langchain_docs = []

                # Reconstruct data
                data = {
                    "transactions": transactions,
                    "vectorstore": vectorstore,
                    "langchain_docs": langchain_docs,
                    "last_updated": user_data.last_updated.isoformat()
                }

                # Update memory cache
                _memory_cache[storage_key] = data

                logger.info(f"📥 PERSISTENT: Loaded {len(transactions)} transactions for '{storage_key}' from PostgreSQL")
                return data
            else:
                logger.warning(f"⚠️ No data found in database for '{storage_key}'")

        except Exception as e:
            logger.error(f"❌ Database load failed for '{storage_key}': {e}")
        finally:
            db.close()

    # Return empty structure if not found
    logger.warning(f"⚠️ No data found for user_id='{user_id}'")
    return {
        "transactions": [],
        "vectorstore": None,
        "langchain_docs": [],
        "last_updated": None
    }


def has_ingested_data(user_id: Optional[str] = None) -> bool:
    """
    Check if data exists for user in cache or database

    Args:
        user_id: Optional user identifier (None for global/legacy storage)

    Returns:
        True if data exists, False otherwise
    """
    storage_key = user_id if user_id else "global"

    # Check memory cache first
    if user_id and storage_key in _memory_cache:
        exists = len(_memory_cache[storage_key].get("transactions", [])) > 0
        logger.info(f"🔍 CACHE: user_id='{user_id}' has data: {exists}")
        return exists

    if not user_id:
        exists = len(_legacy_store["transactions"]) > 0
        logger.info(f"🔍 LEGACY: Global data exists: {exists}")
        return exists

    # Check database
    if DB_AVAILABLE and user_id:
        db = SessionLocal()
        try:
            exists = db.query(UserData).filter_by(user_id=storage_key).first() is not None
            logger.info(f"🔍 PERSISTENT: user_id='{user_id}' has data in DB: {exists}")
            return exists
        except Exception as e:
            logger.error(f"❌ Database check failed: {e}")
            return False
        finally:
            db.close()

    return False


def clear_ingested_data(user_id: Optional[str] = None):
    """
    Delete ingested data from cache and database

    Args:
        user_id: Optional user identifier (None for global/legacy storage)
    """
    storage_key = user_id if user_id else "global"

    # Remove from database
    if DB_AVAILABLE and user_id:
        db = SessionLocal()
        try:
            db.query(UserData).filter_by(user_id=storage_key).delete()
            db.commit()
            logger.info(f"🗑️ Deleted '{storage_key}' from PostgreSQL")
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Database delete failed for '{storage_key}': {e}")
        finally:
            db.close()

    # Remove from memory cache
    if user_id and storage_key in _memory_cache:
        del _memory_cache[storage_key]
        logger.info(f"🗑️ Deleted '{storage_key}' from cache")
    elif not user_id:
        global _legacy_store
        _legacy_store = {
            "transactions": [],
            "vectorstore": None,
            "langchain_docs": [],
            "last_updated": None
        }
        logger.info(f"🗑️ Cleared global/legacy store")


def get_all_users() -> List[str]:
    """Get list of all users who have ingested data"""
    # Check cache first
    if _memory_cache:
        return list(_memory_cache.keys())

    # Load from database
    if DB_AVAILABLE:
        db = SessionLocal()
        try:
            user_ids = [row.user_id for row in db.query(UserData.user_id).all()]
            logger.info(f"📋 Found {len(user_ids)} users in PostgreSQL")
            return user_ids
        except Exception as e:
            logger.error(f"❌ Failed to get user list from database: {e}")
            return []
        finally:
            db.close()

    return []


def get_user_stats() -> Dict[str, Any]:
    """Get statistics about stored user data"""
    # Try database first
    if DB_AVAILABLE:
        db = SessionLocal()
        try:
            users_data = db.query(UserData).all()
            stats = {
                "total_users": len(users_data),
                "users": {
                    user.user_id: {
                        "transactions_count": len(user.transactions),
                        "last_updated": user.last_updated.isoformat()
                    }
                    for user in users_data
                }
            }
            logger.info(f"📊 Retrieved stats for {len(users_data)} users from PostgreSQL")
            return stats
        except Exception as e:
            logger.error(f"❌ Failed to get stats from database: {e}")
        finally:
            db.close()

    # Fallback to memory cache
    return {
        "total_users": len(_memory_cache),
        "users": {
            user_id: {
                "transactions_count": len(data.get("transactions", [])),
                "last_updated": data.get("last_updated")
            }
            for user_id, data in _memory_cache.items()
        }
    }







