from typing import List, Union, Dict
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        # Using high-quality Nomic model for local/Ubuntu hosting
        logger.info(f"Loading local embedding model: {settings.EMBEDDING_MODEL}")
        self.model = TextEmbedding(settings.EMBEDDING_MODEL)
        
        # Load the Reranker locally since we have enough RAM on Ubuntu
        logger.info(f"Loading local reranker model: {settings.RERANKER_MODEL}")
        self.reranker = TextCrossEncoder(settings.RERANKER_MODEL)

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query for searching."""
        res = list(self.model.embed([query]))
        return res[0].tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of documents for storage."""
        res = list(self.model.embed(texts))
        return [vec.tolist() for vec in res]

    def rerank(self, query: str, documents: List[str], top_k: int = 3) -> List[Dict]:
        """
        Rerank documents locally using TextCrossEncoder for maximum accuracy.
        """
        # TextCrossEncoder.rerank returns an iterator of results
        results = list(self.reranker.rerank(query, documents))
        
        # Format for RAG service: list of {'index': int, 'score': float}
        # Sort by score and take top_k
        results.sort(key=lambda x: x.score, reverse=True)
        
        return [{"index": res.index, "score": float(res.score)} for res in results[:top_k]]

# Singleton instance
embedder = EmbeddingService()
