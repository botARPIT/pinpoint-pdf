"""
Centralized configuration using pydantic-settings.
Loads from .env.dev (or .env.prod) based on ENV variable.
"""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration."""
    
    # Environment
    ENV: str = "dev"  # dev | prod
    
    # Database URLs (3 separate Postgres instances)
    USER_DB_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/user_info"
    EMBEDDING_DB_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/embedding_db"
    CHAT_DB_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5434/chat_db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Object storage (S3-compatible)
    STORAGE_PROVIDER: str = "s3"  # s3 | gcs

    # S3 / MinIO
    S3_ENDPOINT: str = "http://localhost:9000"  # MinIO in dev, AWS S3 endpoint in prod
    S3_BUCKET: str = "pinpoint-pdf"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_REGION: str = "us-east-1"

    # Google Cloud Storage (S3-compatible HMAC credentials)
    GOOGLE_STORAGE_ENDPOINT: str = "https://storage.googleapis.com"
    GOOGLE_STORAGE_AUTH_MODE: str = "hmac"  # hmac | adc
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_STORAGE_ACCESS_KEY: str = ""
    GOOGLE_STORAGE_ACCESS_SECRET: str = ""

    # Bucket separation
    RAW_BUCKET: str = "pinpoint-pdf-raw-chunks"
    PROCESSED_BUCKET: str = "pinpoint-pdf-processed"
    
    # Google AI
    GOOGLE_API_KEY: str
    GOOGLE_GENAI_AUTH_MODE: str = "auto"  # auto | api_key | adc
    GEMINI_MODEL: str = "gemini-2.5-flash"
    # Note: gemini-embedding-001 produces 3072 dimensions. text-embedding-004 (768) is unavailable.
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"

    # RAG Tuning
    RAG_TOP_K: int = 5   # Number of chunks to retrieve per query (lower = faster reranking)
    RAG_TOP_N: int = 3   # Number of chunks to pass to LLM
    QUERY_EXPANSION_ENABLED: bool = True
    QUERY_EXPANSION_MIN_WORDS: int = 8

    
    # Vector Store
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX: str = "rag-practice"  # Default to the 3072-dim index
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"
    PINECONE_UPSERT_CONCURRENCY: int = 2
    
    # Supabase settings (currently unused by API auth)
    SUPABASE_URL: str = ""
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_JWKS_URL: str = ""
    SUPABASE_JWT_ISSUER: str = ""
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    SUPABASE_USER_PASSWORD_PLACEHOLDER: str = "__supabase_magic_link__"

    # Local JWT auth
    JWT_SECRET: str = "dev-jwt-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24
    
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    
    # Worker settings
    WORKER_POLL_INTERVAL: int = 2  # seconds
    MAX_RETRIES: int = 3
    WORKER_CHUNK_UPLOAD_BATCH_SIZE: int = 50
    WORKER_CHUNK_UPLOAD_CONCURRENCY: int = 4
    
    # Chunking defaults tuned for retrieval quality + indexing throughput.
    # Typical RAG baseline:
    # - target 250-400 tokens
    # - overlap 15-25%
    TARGET_CHUNK_TOKENS: int = 350
    MAX_CHUNK_TOKENS: int = 600
    MIN_CHUNK_TOKENS: int = 100
    PARAGRAPH_GROUP_SIZE_MIN: int = 1
    PARAGRAPH_GROUP_SIZE_MAX: int = 2
    CHUNK_OVERLAP: int = 30
    ENABLE_TABLE_EXTRACTION: bool = True
    
    # Retrieval
    RETRIEVAL_TOP_K: int = 10
    RERANK_TOP_K: int = 5
    RRF_K: int = 60

    # Embedding throughput
    EMBEDDING_BATCH_SIZE: int = 100
    EMBEDDING_BATCH_CONCURRENCY: int = 2
    
    # LLM
    MAX_CONTEXT_TOKENS: int = 8000
    MAX_OUTPUT_TOKENS: int = 2048  # Increased from hardcoded 500
    TEMPERATURE: float = 0.1
    
    # File limits
    MAX_PDF_SIZE_MB: int = 50
    
    model_config = SettingsConfigDict(
        env_file=".env.dev",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @property
    def supabase_jwt_issuer(self) -> str:
        """Resolve Supabase JWT issuer from explicit value or project URL."""
        if self.SUPABASE_JWT_ISSUER:
            return self.SUPABASE_JWT_ISSUER.rstrip("/")
        if self.SUPABASE_URL:
            return f"{self.SUPABASE_URL.rstrip('/')}/auth/v1"
        return ""

    @property
    def supabase_jwks_url(self) -> str:
        """Resolve Supabase JWKS URL from explicit value or issuer."""
        if self.SUPABASE_JWKS_URL:
            return self.SUPABASE_JWKS_URL
        issuer = self.supabase_jwt_issuer
        if not issuer:
            return ""
        return f"{issuer}/.well-known/jwks.json"

    @model_validator(mode="after")
    def validate_chunking(self):
        """Fail fast on invalid chunking configuration."""
        if self.MIN_CHUNK_TOKENS <= 0:
            raise ValueError("MIN_CHUNK_TOKENS must be > 0")
        if self.TARGET_CHUNK_TOKENS <= self.MIN_CHUNK_TOKENS:
            raise ValueError("TARGET_CHUNK_TOKENS must be greater than MIN_CHUNK_TOKENS")
        if self.MAX_CHUNK_TOKENS < self.TARGET_CHUNK_TOKENS:
            raise ValueError("MAX_CHUNK_TOKENS must be >= TARGET_CHUNK_TOKENS")
        if self.CHUNK_OVERLAP < 0:
            raise ValueError("CHUNK_OVERLAP must be >= 0")
        if self.CHUNK_OVERLAP >= self.TARGET_CHUNK_TOKENS:
            raise ValueError("CHUNK_OVERLAP must be less than TARGET_CHUNK_TOKENS")
        if self.EMBEDDING_BATCH_SIZE <= 0:
            raise ValueError("EMBEDDING_BATCH_SIZE must be > 0")
        if self.EMBEDDING_BATCH_CONCURRENCY <= 0:
            raise ValueError("EMBEDDING_BATCH_CONCURRENCY must be > 0")
        if self.PINECONE_UPSERT_CONCURRENCY <= 0:
            raise ValueError("PINECONE_UPSERT_CONCURRENCY must be > 0")
        if self.WORKER_CHUNK_UPLOAD_BATCH_SIZE <= 0:
            raise ValueError("WORKER_CHUNK_UPLOAD_BATCH_SIZE must be > 0")
        if self.WORKER_CHUNK_UPLOAD_CONCURRENCY <= 0:
            raise ValueError("WORKER_CHUNK_UPLOAD_CONCURRENCY must be > 0")
        if self.QUERY_EXPANSION_MIN_WORDS <= 0:
            raise ValueError("QUERY_EXPANSION_MIN_WORDS must be > 0")
        if self.RAG_TOP_K <= 0:
            raise ValueError("RAG_TOP_K must be > 0")
        if self.RAG_TOP_N <= 0:
            raise ValueError("RAG_TOP_N must be > 0")
        if self.RAG_TOP_N > self.RAG_TOP_K:
            raise ValueError("RAG_TOP_N must be <= RAG_TOP_K")
        return self


# Global settings instance
settings = Settings()
