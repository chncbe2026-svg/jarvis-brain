from typing import List, Union, Dict
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        # Using high-quality Nomic model for local/Ubuntu hosting
        # Using the home directory for cache to ensure full write permissions
        cache_dir = "/home/jarvis/.fastembed_cache"
        self.model = TextEmbedding(settings.EMBEDDING_MODEL, threads=1, cache_dir=cache_dir)
        
        # Load the Reranker locally since we have enough RAM on Ubuntu
        logger.info(f"Loading local reranker model: {settings.RERANKER_MODEL}")
        
        # Handle outdated model string from .env
        reranker_model = settings.RERANKER_MODEL
        if reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2":
            reranker_model = "Xenova/ms-marco-MiniLM-L-6-v2"
            
        try:
            self.reranker = TextCrossEncoder(reranker_model, threads=1, cache_dir=cache_dir)
        except ValueError:
            logger.warning(f"Reranker {reranker_model} not supported, falling back to BAAI/bge-reranker-base")
            self.reranker = TextCrossEncoder("BAAI/bge-reranker-base", threads=1)

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
        Handles both RerankResult objects and raw scores.
        """
        try:
            # Try the standard rerank method
            raw_results = list(self.reranker.rerank(query, documents))
            
            # Check if results are objects with .score or just floats
            if not raw_results:
                return []
                
            formatted_results = []
            if hasattr(raw_results[0], "score"):
                # Case 1: Iterator of RerankResult objects (Standard)
                for res in raw_results:
                    formatted_results.append({"index": res.index, "score": float(res.score)})
            else:
                # Case 2: Iterator of raw float scores (Fallback)
                for i, score in enumerate(raw_results):
                    formatted_results.append({"index": i, "score": float(score)})
            
            # Sort by score and take top_k
            formatted_results.sort(key=lambda x: x["score"], reverse=True)
            return formatted_results[:top_k]
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Fallback: just return the first few original documents if reranking fails
            return [{"index": i, "score": 1.0} for i in range(min(top_k, len(documents)))]

# Singleton instance
embedder = EmbeddingService()
