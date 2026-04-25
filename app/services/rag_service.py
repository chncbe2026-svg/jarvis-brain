import uuid
from typing import List, Optional, Dict, Any
from groq import Groq
from app.core.config import settings
from app.services.qdrant_client import qdrant
from app.services.embedding_service import embedder
from qdrant_client.http import models
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, Range
from rank_bm25 import BM25Okapi
import logging

logger = logging.getLogger(__name__)
groq_client = Groq(api_key=settings.GROQ_API_KEY)

def chunk_text_simple(text: str, chunk_size: int = 2000, overlap: int = 400) -> List[str]:
    """Simple character-based chunking to replace tiktoken and save RAM."""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return chunks

def build_filter(filters: Optional[Dict[str, Any]] = None) -> Optional[Filter]:
    if not filters:
        return None
    
    conditions = []
    if "vendor" in filters:
        conditions.append(FieldCondition(key="vendor", match=MatchValue(value=filters["vendor"])))
    if "severity" in filters:
        conditions.append(FieldCondition(key="severity", match=MatchValue(value=filters["severity"])))
    
    return Filter(must=conditions) if conditions else None

def hybrid_search(
    query: str, 
    collection: str, 
    top_k: int = 10,
    qdrant_filter: Optional[Filter] = None
) -> List[Dict]:
    """
    Combines Semantic (Dense) search and BM25 (Keyword) search.
    """
    # 1. Semantic Search
    query_vector = embedder.embed_query(query)
    search_response = qdrant.query_points(
        collection_name=collection,
        query=query_vector,
        query_filter=qdrant_filter,
        limit=top_k,
        with_payload=True,
    )
    semantic_hits = search_response.points

    # 2. BM25 Search
    try:
        scroll_results, _ = qdrant.scroll(
            collection_name=collection,
            scroll_filter=qdrant_filter,
            limit=200,
            with_payload=True,
        )
    except Exception:
        scroll_results = []

    docs = [r.payload.get("text", "") for r in scroll_results]
    doc_ids = [str(r.id) for r in scroll_results]

    bm25_scores = {}
    if docs:
        tokenized = [d.lower().split() for d in docs]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(query.lower().split())
        bm25_scores = {doc_ids[i]: float(scores[i]) for i in range(len(doc_ids))}

    # 3. Fuse Results (Simple Linear Combination)
    sem_map = {str(hit.id): hit.score for hit in semantic_hits}
    sem_payloads = {str(hit.id): hit.payload for hit in semantic_hits}
    
    # Reciprocal Rank Fusion or simple weighted sum
    alpha = settings.HYBRID_ALPHA
    combined = []
    all_ids = set(sem_map.keys()) | set(bm25_scores.keys())

    for doc_id in all_ids:
        s_score = sem_map.get(doc_id, 0.0)
        b_score = bm25_scores.get(doc_id, 0.0)
        
        # Normalise scores (rough)
        fused_score = (alpha * s_score) + ((1 - alpha) * (b_score / 10.0))
        
        # Get payload
        payload = sem_payloads.get(doc_id)
        if not payload:
            # Try to find in scroll results
            for r in scroll_results:
                if str(r.id) == doc_id:
                    payload = r.payload
                    break

        if payload:
            combined.append({"id": doc_id, "score": fused_score, "payload": payload})

    combined.sort(key=lambda x: x["score"], reverse=True)
    return combined[:top_k]

class RAGService:
    def chunk_text(self, text: str) -> List[str]:
        return chunk_text_simple(text)

    async def ingest_text(self, text: str, metadata: Dict[str, Any], collection: str) -> int:
        chunks = self.chunk_text(text)
        embeddings = embedder.embed_batch(chunks)

        points = [
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload={"text": chunk, **metadata},
            )
            for chunk, emb in zip(chunks, embeddings)
        ]

        qdrant.upsert(collection_name=collection, points=points)
        return len(points)

    async def query(
        self,
        user_query: str,
        collection: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        target_collections = [collection] if collection else [
            settings.COLLECTION_PERSONAL,
            settings.COLLECTION_NETWORK,
            settings.COLLECTION_VENDOR,
        ]

        qdrant_filter = build_filter(filters)
        all_candidates = []

        for coll in target_collections:
            try:
                hits = hybrid_search(user_query, coll, settings.TOP_K_RETRIEVE, qdrant_filter)
                all_candidates.extend(hits)
            except Exception as e:
                logger.warning(f"Search failed in {coll}: {e}")

        if not all_candidates:
            return {"answer": "Sir, I found no relevant information in the knowledge base.", "sources": []}

        # Reranking using Local CrossEncoder (High Accuracy)
        doc_texts = [c["payload"].get("text", "") for c in all_candidates]
        rerank_results = embedder.rerank(user_query, doc_texts, settings.TOP_K_RERANK)
        
        final_docs = []
        for res in rerank_results:
            final_docs.append(all_candidates[res["index"]])

        # Build context
        context_blocks = []
        sources = []
        for i, doc in enumerate(final_docs, 1):
            p = doc["payload"]
            title = p.get("title", "Unknown")
            vendor = p.get("vendor", "System")
            context_blocks.append(f"### Source {i}: {title}\n{p.get('text', '')}")
            sources.append({
                "id": i, "title": title, "vendor": vendor, 
                "severity": p.get("severity", ""), "link": p.get("link", "")
            })

        context_str = "\n\n".join(context_blocks)
        
        system_prompt = """You are JARVIS — a highly capable IT and Security assistant.
Use the CONTEXT provided to answer the QUESTION. Cite sources using [1], [2].
If the CONTEXT is irrelevant, use your general knowledge but mention you are doing so."""

        user_prompt = f"CONTEXT:\n{context_str}\n\nQUESTION:\n{user_query}"

        response = groq_client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.1
        )

        return {"answer": response.choices[0].message.content, "sources": sources}

rag_service = RAGService()

def get_rag_service() -> RAGService:
    return rag_service
