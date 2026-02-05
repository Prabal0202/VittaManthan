"""
Configuration settings for the application
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings:
    """Application settings"""

    # API Configuration
    APP_TITLE: str = "Transaction RAG Service"
    APP_DESCRIPTION: str = "LLM-powered transaction query service with multilingual support"
    APP_VERSION: str = "1.0.0"

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 9000
    RELOAD: bool = True

    # CORS Configuration - Allows access from Netlify app and local development
    # Can be overridden via ALLOW_ORIGINS environment variable (comma-separated)
    ALLOW_ORIGINS: list = os.getenv("ALLOW_ORIGINS",
        "https://vittamanthan.netlify.app,"
        "http://localhost:5173,"
        "http://localhost:3000,"
        "http://localhost:8000,"
        "http://localhost:9000,"
        "http://127.0.0.1:5173,"
        "http://127.0.0.1:3000"
    ).split(",")

    ALLOW_CREDENTIALS: bool = True
    ALLOW_METHODS: list = ["*"]  # Allow all HTTP methods (GET, POST, PUT, DELETE, PATCH, OPTIONS)
    ALLOW_HEADERS: list = ["*"]  # Allow all headers (Content-Type, Authorization, X-Requested-With, etc.)

    # OpenAI/LLM Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = "https://openrouter.ai/api/v1"

    # LLM Model Configuration (can be set via environment variable)
    LLM_MODEL: str = os.getenv("LLM_MODEL", "arcee-ai/trinity-large-preview:free")

    # Free LLM models to try (reference list)
    FREE_MODELS: list = [
        "arcee-ai/trinity-large-preview:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "openai/gpt-oss-120b:free",
        "meta-llama/llama-3.2-3b-instruct:free",
        "xiaomi/mimo-v2-flash:free",
        "microsoft/phi-3-mini-128k-instruct:free",
        "qwen/qwen-2-7b-instruct:free",
    ]

    # LLM Parameters
    LLM_TEMPERATURE: float = 0.8
    LLM_MAX_TOKENS: int = 3000
    LLM_TOP_P: float = 0.9
    LLM_FREQUENCY_PENALTY: float = 0.3
    LLM_PRESENCE_PENALTY: float = 0.3

    # Embedding Model
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Cache Configuration
    CACHE_TTL_MINUTES: int = 30


settings = Settings()
