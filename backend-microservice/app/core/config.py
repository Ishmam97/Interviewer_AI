"""
Configuration settings for the AI Interview Assistant Backend (Firebase + Gemini)
"""

import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "AI Interview Assistant Backend"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # CORS — base list; extend at runtime via CORS_ALLOWED_ORIGINS (comma-separated)
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8501",
        "http://localhost:8000",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://localhost:5173",
        "https://interviewerai-ias.web.app",
        "https://interviewerai-ias.firebaseapp.com",
    ]
    CORS_ALLOWED_ORIGINS: str = ""  # comma-separated extra origins (e.g. LAN IP)

    @property
    def cors_origins(self) -> List[str]:
        extras = [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]
        base = self.ALLOWED_ORIGINS
        if self.ENVIRONMENT == "production":
            # Don't ship localhost origins in a production CORS allow-list —
            # they're never a legitimate caller of a deployed API.
            base = [o for o in base if "localhost" not in o]
        return list(dict.fromkeys(base + extras))

    # Firebase
    FIREBASE_SERVICE_ACCOUNT_PATH: str = os.getenv(
        "FIREBASE_SERVICE_ACCOUNT_PATH", "./firebase-service-account.json"
    )
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "interviewer-ea164")
    FIREBASE_API_KEY: str = os.getenv("FIREBASE_API_KEY", "")

    # AI/ML — system-level keys (used as fallback when user has no personal key)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")   # e.g. https://api.aimlapi.com/v1
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-4.1-nano-2025-04-14")

    # AIML API model IDs (config-driven so a model change / outage is an env edit,
    # not a code change). Override via env if the provider retires an ID.
    AIML_BASE_URL: str = os.getenv("AIML_BASE_URL", "https://api.aimlapi.com/v1")
    RESUME_PARSE_MODEL: str = os.getenv("RESUME_PARSE_MODEL", "openai/gpt-5-nano-2025-08-07")
    RESUME_SECTION_MODEL: str = os.getenv("RESUME_SECTION_MODEL", "openai/gpt-5-nano-2025-08-07")
    RESUME_HOLISTIC_MODEL: str = os.getenv("RESUME_HOLISTIC_MODEL", "moonshot/kimi-k2-0905-preview")
    DREAM_JOB_NORMALIZE_MODEL: str = os.getenv("DREAM_JOB_NORMALIZE_MODEL", "openai/gpt-5-nano-2025-08-07")
    DREAM_JOB_FIT_MODEL: str = os.getenv("DREAM_JOB_FIT_MODEL", "moonshot/kimi-k2-0905-preview")
    SUGGESTION_APPLY_MODEL: str = os.getenv("SUGGESTION_APPLY_MODEL", "openai/gpt-4.1-mini-2025-04-14")

    # Interview Configuration
    MAX_QUESTIONS: int = int(os.getenv("MAX_QUESTIONS", "5"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "800"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "150"))
    RAG_K_RESULTS: int = int(os.getenv("RAG_K_RESULTS", "3"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.3"))

    # File Storage
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./data")
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".txt", ".doc", ".docx"]

    # Vector Store
    VECTOR_STORE_PATH: str = os.getenv("VECTOR_STORE_PATH", "./vector_stores")
    INDEX_PATH: str = os.getenv(
        "INDEX_PATH", "./vector_stores/interview_faiss_index"
    )

    # Observability — Sentry is opt-in: with no DSN set, init is skipped
    # entirely so local/dev runs and CI never phone home.
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    SENTRY_TRACES_SAMPLE_RATE: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")

    # Reports
    REPORTS_DIR: str = os.getenv("REPORTS_DIR", "./reports")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
