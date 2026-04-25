from typing import List, Union
from mixedbread_ai.client import MixedbreadAI
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        if not settings.MIXEDBREAD_API_KEY:
            logger.warning("MIXEDBREAD_API_KEY not found! Embeddings will fail.")
        
        self.client = MixedbreadAI(api_key=settings.MIXEDBREAD_API_KEY)
        self.model = settings.EMBEDDING_MODEL

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query for searching."""
        res = self.client.embeddings(
            model=self.model,
            input=query,
            normalized=True
        )
        return res.data[0].embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of documents for storage."""
        # Mixedbread handles batching automatically
        res = self.client.embeddings(
            model=self.model,
            input=texts,
            normalized=True
        )
        return [item.embedding for item in res.data]

    def rerank(self, query: str, documents: List[str], top_k: int = 3) -> List[dict]:
        """
        Rerank a list of documents based on query relevance using Mixedbread API.
        Returns list of {'index': int, 'score': float}
        """
        res = self.client.reranking(
            model=settings.RERANKER_MODEL,
            query=query,
            input=documents,
            top_n=top_k
        )
        return [{"index": item.index, "score": item.score} for item in res.data]

# Singleton instance
embedder = EmbeddingService()
