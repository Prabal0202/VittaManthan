"""
Health check and status endpoints
"""

from fastapi import APIRouter, Query
from typing import Optional
from app.utils.data_store import get_ingested_data, get_user_stats, has_ingested_data
from app.utils.chat_history import (
    get_chat_history,
    get_recent_queries,
    get_chat_statistics,
    delete_chat_history
)

router = APIRouter()

# Global references to models (will be set by main app)
embeddings_model = None
llm = None


def set_models(emb_model, llm_model):
    """Set global model references"""
    global embeddings_model, llm
    embeddings_model = emb_model
    llm = llm_model


@router.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Transaction RAG Service",
        "version": "2.0.0",
        "models_loaded": embeddings_model is not None and llm is not None,
        "cors_enabled": True,
        "allowed_origins": [
            "https://vittamanthan.netlify.app",
            "http://localhost:5173",
            "http://localhost:3000"
        ]
    }


@router.get("/cors-test")
async def cors_test():
    """
    Test endpoint to verify CORS is working
    Call this from your frontend to check CORS configuration
    """
    return {
        "status": "success",
        "message": "CORS is working! If you can see this, your frontend can access the API.",
        "timestamp": "2026-02-05",
        "cors_headers": {
            "Access-Control-Allow-Origin": "Handled by FastAPI middleware",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*"
        }
    }



@router.get("/status")
async def get_ingestion_status():
    """Check the status of ingested context data (global/legacy)"""
    ingested_data = get_ingested_data()

    return {
        "data_ingested": len(ingested_data["transactions"]) > 0,
        "transactions_count": len(ingested_data["transactions"]),
        "last_updated": ingested_data["last_updated"],
        "vectorstore_ready": ingested_data["vectorstore"] is not None
    }


@router.get("/status/users")
async def get_all_users_status():
    """Check the status of all users' ingested data"""
    user_stats = get_user_stats()
    global_has_data = has_ingested_data(user_id=None)

    return {
        "multi_user_stats": user_stats,
        "global_data_exists": global_has_data,
        "message": "Use user_id in /ingest and /prompt endpoints for multi-user isolation"
    }


@router.post("/test-connection")
async def test_connection():
    """Test LLM connection"""
    if not llm:
        return {"status": "error", "error": "LLM not initialized"}

    try:
        response = llm.invoke("Hello")
        return {"status": "success", "message": "LLM is working", "response": str(response.content)[:100]}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/history/{user_id}")
async def get_user_chat_history(
    user_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get chat history for a specific user

    Args:
        user_id: User identifier
        limit: Maximum number of entries to return (1-100)
        offset: Number of entries to skip for pagination
    """
    history = get_chat_history(user_id, limit=limit, offset=offset)
    return {
        "user_id": user_id,
        "history": history,
        "count": len(history),
        "limit": limit,
        "offset": offset
    }


@router.get("/history/{user_id}/recent")
async def get_user_recent_queries(
    user_id: str,
    limit: int = Query(10, ge=1, le=50)
):
    """
    Get recent queries for a user (useful for query suggestions)

    Args:
        user_id: User identifier
        limit: Maximum number of queries to return (1-50)
    """
    queries = get_recent_queries(user_id, limit=limit)
    return {
        "user_id": user_id,
        "recent_queries": queries,
        "count": len(queries)
    }


@router.get("/history/{user_id}/stats")
async def get_user_chat_stats(user_id: str):
    """
    Get chat statistics for a user

    Args:
        user_id: User identifier
    """
    stats = get_chat_statistics(user_id)
    return stats


@router.delete("/history/{user_id}")
async def delete_user_chat_history(user_id: str):
    """
    Delete all chat history for a user

    Args:
        user_id: User identifier
    """
    delete_chat_history(user_id)
    return {
        "status": "success",
        "message": f"Chat history deleted for user '{user_id}'"
    }

