from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.core.config import settings
import os

# Determine connection mode: Cloud > Local > In-Memory
if settings.QDRANT_URL and settings.QDRANT_API_KEY:
    print(f"[Qdrant] Connecting to Qdrant Cloud: {settings.QDRANT_URL}")
    qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
else:
    # On Render, we usually use Cloud, but fallback to localhost
    _USE_MEMORY = settings.QDRANT_HOST in ("localhost", "127.0.0.1") and os.environ.get("QDRANT_FORCE_REMOTE") != "1"
    if _USE_MEMORY:
        print("[Qdrant] Using in-memory mode (local dev). Data resets on restart.")
        qdrant = QdrantClient(":memory:")
    else:
        print(f"[Qdrant] Connecting to local server: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
        qdrant = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

def init_collections():
    collections = [
        settings.COLLECTION_PERSONAL,
        settings.COLLECTION_NETWORK,
        settings.COLLECTION_VENDOR
    ]
    
    try:
        existing = [c.name for c in qdrant.get_collections().collections]
    except Exception as e:
        print(f"[Qdrant] Error getting collections: {e}")
        existing = []
    
    for coll in collections:
        if coll not in existing:
            qdrant.create_collection(
                collection_name=coll,
                vectors_config=models.VectorParams(
                    size=1024,  # mxbai-embed-large-v1 size
                    distance=models.Distance.COSINE
                )
            )
            print(f"[Qdrant] Created collection: {coll}")

def get_qdrant_client():
    return qdrant

# For easier imports
client = qdrant
