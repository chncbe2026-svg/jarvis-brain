from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.core.config import settings
import os

# Determine connection mode: Cloud > Local > In-Memory
if settings.QDRANT_URL and settings.QDRANT_API_KEY:
    print(f"[Qdrant] Connecting to Qdrant Cloud: {settings.QDRANT_URL}")
    qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
else:
    # On Ubuntu, we usually connect to the 'qdrant' service in docker
    _USE_MEMORY = settings.QDRANT_HOST in ("localhost", "127.0.0.1") and os.environ.get("QDRANT_FORCE_REMOTE") != "1"
    if _USE_MEMORY:
        print("[Qdrant] Using in-memory mode (local dev). Data resets on restart.")
        qdrant = QdrantClient(":memory:")
    else:
        print(f"[Qdrant] Connecting to local/docker server: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
        qdrant = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

def init_collections():
    collections = [
        settings.COLLECTION_PERSONAL,
        settings.COLLECTION_NETWORK,
        settings.COLLECTION_VENDOR
    ]
    
    try:
        existing_colls = qdrant.get_collections().collections
        existing = {c.name: c for c in existing_colls}
    except Exception as e:
        print(f"[Qdrant] Error getting collections: {e}")
        existing = {}
    
    for coll in collections:
        if coll not in existing:
            qdrant.create_collection(
                collection_name=coll,
                vectors_config=models.VectorParams(
                    size=768,  # Nomic-embed-text size
                    distance=models.Distance.COSINE
                )
            )
            print(f"[Qdrant] Created collection: {coll}")
        else:
            # If the collection exists but has wrong dimensions, recreate it
            info = qdrant.get_collection(coll)
            if info.config.params.vectors.size != 768:
                print(f"[Qdrant] Recreating {coll} due to dimension mismatch...")
                qdrant.delete_collection(coll)
                qdrant.create_collection(
                    collection_name=coll,
                    vectors_config=models.VectorParams(
                        size=768,
                        distance=models.Distance.COSINE
                    )
                )

def get_qdrant_client():
    return qdrant

# For easier imports
client = qdrant
