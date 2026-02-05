"""
Main FastAPI Application
Transaction RAG Service with LLM-powered querying and PostgreSQL persistence
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.services.embeddings import HuggingFaceEmbeddings
from app.services.llm import initialize_llm
from app.api import health, transactions

# Import database initialization
try:
    from app.db.database import init_db, test_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global model instances
embeddings_model = None
llm = None
llm_streaming = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown
    """
    global embeddings_model, llm, llm_streaming

    # Startup
    logger.info("🚀 Starting FastAPI RAG Service...")

    try:
        # Initialize database
        if DB_AVAILABLE:
            logger.info("Initializing PostgreSQL database...")
            init_db()
            if test_connection():
                logger.info("✅ Database initialized and connected successfully")
            else:
                logger.warning("⚠️ Database connection failed - using in-memory storage only")
        else:
            logger.warning("⚠️ Database module not available - using in-memory storage only")

        logger.info("Initializing embedding model...")
        embeddings_model = HuggingFaceEmbeddings(settings.EMBEDDING_MODEL)
        logger.info("✅ Embedding model initialized")

        logger.info("Initializing LLM...")
        llm = initialize_llm(streaming=False)
        logger.info("✅ LLM initialized")

        logger.info("Initializing LLM for streaming...")
        llm_streaming = initialize_llm(streaming=True)
        logger.info("✅ LLM streaming initialized")

        # Set models in routers
        health.set_models(embeddings_model, llm)
        transactions.set_models(embeddings_model, llm, llm_streaming)

        logger.info("🎉 Application startup complete!")

    except Exception as e:
        logger.error(f"❌ Failed to initialize application: {e}")
        raise

    yield

    # Shutdown (cleanup if needed)
    logger.info("Shutting down...")



# Create FastAPI app
app = FastAPI(
    title="RAG Transaction Service with PostgreSQL Persistence",
    description="Multi-user RAG service with persistent storage, chat history, and streaming support",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware - Configured for Netlify app access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS,  # Includes https://vittamanthan.netlify.app
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_methods=settings.ALLOW_METHODS,  # All HTTP methods (GET, POST, PUT, DELETE, OPTIONS, etc.)
    allow_headers=settings.ALLOW_HEADERS,  # All headers including Content-Type, Authorization, etc.
    expose_headers=["*"],  # Expose all response headers to frontend
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(transactions.router, tags=["Transactions"])
