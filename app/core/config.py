from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    GROQ_API_KEY: str
    MIXEDBREAD_API_KEY: str = ""
    
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    
    COLLECTION_PERSONAL: str = "personal_memory"
    COLLECTION_NETWORK: str = "network_knowledge"
    COLLECTION_VENDOR: str = "vendor_news"
    
    # We use Mixedbread for embeddings now
    EMBEDDING_MODEL: str = "mixedbread-ai/mxbai-embed-large-v1"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    RERANKER_MODEL: str = "mixedbread-ai/mxbai-rerank-large-v1"
    
    # RAG Pipeline tuning
    CHUNK_SIZE: int = 600        # in tokens
    CHUNK_OVERLAP: int = 120     # in tokens
    HYBRID_ALPHA: float = 0.7    # 0=pure BM25, 1=pure semantic, 0.7=balanced
    TOP_K_RETRIEVE: int = 10     # chunks to retrieve before reranking
    TOP_K_RERANK: int = 3        # chunks to keep after reranking
    
    # Scheduling
    RSS_SYNC_INTERVAL_MINS: int = 30

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
