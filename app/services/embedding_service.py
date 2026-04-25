from typing import List, Union
from fastembed import TextEmbedding
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        # We use a very small model (all-MiniLM-L6-v2) to ensure it fits in Render's 512MB RAM
        logger.info(f"Loading local embedding model: {settings.EMBEDDING_MODEL}")
        self.model = TextEmbedding(settings.EMBEDDING_MODEL)

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query for searching."""
        res = list(self.model.embed([query]))
        return res[0].tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of documents for storage."""
        res = list(self.model.embed(texts))
        return [vec.tolist() for vec in res]

# Singleton instance
embedder = EmbeddingService()
