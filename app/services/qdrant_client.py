from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.core.config import get_settings
import os

settings = get_settings()

# Determine connection mode: Cloud > Local > In-Memory
if settings.QDRANT_URL and settings.QDRANT_API_KEY:
    print(f"[Qdrant] Connecting to Qdrant Cloud: {settings.QDRANT_URL}")
    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
else:
    _USE_MEMORY = settings.QDRANT_HOST in ("localhost", "127.0.0.1") and os.environ.get("QDRANT_FORCE_REMOTE") != "1"
    if _USE_MEMORY:
        print("[Qdrant] Using in-memory mode (local dev). Data resets on restart.")
        client = QdrantClient(":memory:")
    else:
        print(f"[Qdrant] Connecting to local server: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
        client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

def init_collections():
    collections = [
        settings.COLLECTION_PERSONAL,
        settings.COLLECTION_NETWORK,
        settings.COLLECTION_VENDOR
    ]
    
    existing = [c.name for c in client.get_collections().collections]
    
    for coll in collections:
        if coll not in existing:
            client.create_collection(
                collection_name=coll,
                vectors_config=models.VectorParams(
                    size=768,  # nomic-embed-text-v1.5 output dim (bge-small = 384)
                    distance=models.Distance.COSINE
                )
            )
            print(f"[Qdrant] Created collection: {coll}")

def get_qdrant_client():
    return client
