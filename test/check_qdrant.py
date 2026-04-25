import sys
sys.path.insert(0, '.')
from app.services.qdrant_client import get_qdrant_client, init_collections
from app.core.config import get_settings

settings = get_settings()
init_collections()
q = get_qdrant_client()

info = q.get_collection(settings.COLLECTION_VENDOR)
print(f"vendor_news vectors count: {info.vectors_count}")

results, _ = q.scroll(
    collection_name=settings.COLLECTION_VENDOR,
    limit=10,
    with_payload=True,
    with_vectors=False
)
print(f"Scrolled rows: {len(results)}")
for r in results:
    vendor = r.payload.get("vendor", "?")
    severity = r.payload.get("severity", "?")
    text = r.payload.get("text", "")[:80]
    print(f"  - {vendor} | {severity} | {text}")
