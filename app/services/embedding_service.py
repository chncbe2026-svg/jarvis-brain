from fastembed import TextEmbedding
from typing import List
from app.core.config import get_settings

settings = get_settings()

class EmbeddingService:
    def __init__(self):
        # This will download the model on first use
        self.model = TextEmbedding(model_name=settings.EMBEDDING_MODEL)

    def embed_text(self, text: str) -> List[float]:
        embeddings = list(self.model.embed([text]))
        return embeddings[0].tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [e.tolist() for e in self.model.embed(texts)]

embedding_service = EmbeddingService()

def get_embedding_service():
    return embedding_service
