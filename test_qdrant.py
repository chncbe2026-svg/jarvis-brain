from qdrant_client import QdrantClient
from fastembed import TextEmbedding

qdrant = QdrantClient(host='192.168.10.152', port=6333)
embedder = TextEmbedding('nomic-ai/nomic-embed-text-v1.5')
vec = list(embedder.embed(['Cisco security']))[0].tolist()

try:
    res = qdrant.query_points('vendor_news', query=vec, limit=5, with_payload=True)
    print("SUCCESS")
except Exception as e:
    print(f"ERROR: {e}")
