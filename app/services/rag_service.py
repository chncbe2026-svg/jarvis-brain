import uuid
from typing import List, Optional, Dict, Any
from groq import Groq
from app.core.config import get_settings
from app.services.qdrant_client import get_qdrant_client
from app.services.embedding_service import get_embedding_service
from qdrant_client.http import models
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, Range
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
import tiktoken
import logging

logger = logging.getLogger(__name__)
settings = get_settings()
qdrant = get_qdrant_client()
embedder = get_embedding_service()
groq_client = Groq(api_key=settings.GROQ_API_KEY)

# ─── Lazy-loaded cross-encoder reranker ────────────────────────────────────────
_reranker: Optional[CrossEncoder] = None

def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        logger.info("Loading cross-encoder reranker…")
        _reranker = CrossEncoder(settings.RERANKER_MODEL)
    return _reranker

# ─── Token-aware chunker using tiktoken ────────────────────────────────────────
def chunk_text_by_tokens(text: str) -> List[str]:
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + settings.CHUNK_SIZE
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        start += settings.CHUNK_SIZE - settings.CHUNK_OVERLAP
    return [c for c in chunks if c.strip()]


# ─── Metadata filter builder ────────────────────────────────────────────────────
def build_filter(filters: Optional[Dict[str, Any]]) -> Optional[Filter]:
    """
    Convert a dict like {"vendor": "Cisco", "severity": "Critical"}
    into a Qdrant Filter object.
    """
    if not filters:
        return None

    conditions = []
    for key, value in filters.items():
        if key == "published_after":
            # Range filter: published >= date string
            conditions.append(
                models.FieldCondition(
                    key="published",
                    range=models.Range(gte=value)
                )
            )
        else:
            conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=value)
                )
            )

    return Filter(must=conditions)


# ─── Hybrid retrieval ──────────────────────────────────────────────────────────
def hybrid_search(
    query: str,
    collection: str,
    top_k: int,
    qdrant_filter: Optional[Filter] = None
) -> List[Dict]:
    """
    Fuse semantic vector search with BM25 keyword search.
    Returns a merged ranked list with original payload.
    """
    # 1. Semantic search (qdrant-client v1.8+ uses query_points)
    query_vector = embedder.embed_text(query)
    try:
        semantic_result = qdrant.query_points(
            collection_name=collection,
            query=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )
        semantic_hits = semantic_result.points
    except AttributeError:
        # Fallback for older client versions
        semantic_hits = qdrant.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )

    # 2. Scroll all candidate docs for BM25
    try:
        scroll_results, _ = qdrant.scroll(
            collection_name=collection,
            scroll_filter=qdrant_filter,
            limit=200,
            with_payload=True,
            with_vectors=False,
        )
    except Exception:
        scroll_results = []

    # 3. BM25 over scrolled candidates
    docs = [r.payload.get("text", "") for r in scroll_results]
    doc_ids = [str(r.id) for r in scroll_results]

    bm25_scores: Dict[str, float] = {}
    if docs:
        tokenized = [d.lower().split() for d in docs]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(query.lower().split())
        bm25_scores = {doc_ids[i]: float(scores[i]) for i in range(len(doc_ids))}

    # 4. Normalise semantic scores
    sem_map: Dict[str, float] = {}
    sem_payloads: Dict[str, Dict] = {}
    for hit in semantic_hits:
        sem_map[str(hit.id)] = hit.score
        sem_payloads[str(hit.id)] = hit.payload

    # Collect all unique IDs from both sources
    all_ids = set(sem_map.keys()) | set(bm25_scores.keys())

    # Min-max normalise BM25
    bm25_vals = list(bm25_scores.values())
    bm25_min = min(bm25_vals) if bm25_vals else 0
    bm25_max = max(bm25_vals) if bm25_vals else 1
    bm25_range = bm25_max - bm25_min or 1

    # Min-max normalise semantic
    sem_vals = list(sem_map.values())
    sem_min = min(sem_vals) if sem_vals else 0
    sem_max = max(sem_vals) if sem_vals else 1
    sem_range = sem_max - sem_min or 1

    # 5. Reciprocal Rank Fusion-style score with alpha weighting
    fused: List[Dict] = []
    for doc_id in all_ids:
        sem_norm = (sem_map.get(doc_id, 0) - sem_min) / sem_range
        bm25_norm = (bm25_scores.get(doc_id, 0) - bm25_min) / bm25_range

        final_score = (
            settings.HYBRID_ALPHA * sem_norm
            + (1 - settings.HYBRID_ALPHA) * bm25_norm
        )

        # Retrieve payload — prefer semantic hits (they have vectors)
        payload = sem_payloads.get(doc_id)
        if payload is None:
            # Fall back to scrolled results
            for r in scroll_results:
                if str(r.id) == doc_id:
                    payload = r.payload
                    break

        if payload:
            fused.append({"id": doc_id, "score": final_score, "payload": payload})

    fused.sort(key=lambda x: x["score"], reverse=True)
    return fused[:top_k]


# ─── Cross-encoder reranker ─────────────────────────────────────────────────────
def rerank(query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
    """
    Score (query, passage) pairs with a cross-encoder, return top_k.
    """
    if not candidates:
        return []

    reranker = get_reranker()
    pairs = [(query, c["payload"].get("text", "")) for c in candidates]
    scores = reranker.predict(pairs)

    for i, c in enumerate(candidates):
        c["rerank_score"] = float(scores[i])

    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
    return candidates[:top_k]


# ─── Core RAG class ─────────────────────────────────────────────────────────────
class RAGService:

    def chunk_text(self, text: str) -> List[str]:
        return chunk_text_by_tokens(text)

    async def ingest_text(
        self,
        text: str,
        metadata: Dict[str, Any],
        collection: str,
    ) -> int:
        """
        Chunk text, embed, and store in Qdrant with rich metadata.
        Expected metadata keys: vendor, severity, published, source, title, link, filename, type
        """
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
        logger.info(f"Ingested {len(points)} chunks into '{collection}'")
        return len(points)

    async def query(
        self,
        user_query: str,
        collection: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Full pipeline:
          Hybrid Search → Metadata Filter → Cross-Encoder Rerank → Groq → Cited Answer
        """
        target_collections = (
            [collection]
            if collection
            else [
                settings.COLLECTION_PERSONAL,
                settings.COLLECTION_NETWORK,
                settings.COLLECTION_VENDOR,
            ]
        )

        qdrant_filter = build_filter(filters)
        all_candidates: List[Dict] = []

        # 1. Hybrid retrieval across collections
        for coll in target_collections:
            try:
                hits = hybrid_search(
                    query=user_query,
                    collection=coll,
                    top_k=settings.TOP_K_RETRIEVE,
                    qdrant_filter=qdrant_filter,
                )
                all_candidates.extend(hits)
            except Exception as e:
                logger.warning(f"Collection '{coll}' search failed: {e}")

        # Sort fused results across collections
        all_candidates.sort(key=lambda x: x["score"], reverse=True)
        all_candidates = all_candidates[: settings.TOP_K_RETRIEVE]

        # 2. Hallucination safeguard — no context found
        if not all_candidates:
            return {
                "answer": (
                    "Sir, I found no evidence in the knowledge base to answer your question. "
                    "I will not speculate. Please ensure relevant documents have been ingested."
                ),
                "sources": [],
                "filters_applied": filters or {},
            }

        # 3. Cross-encoder reranking
        reranked = rerank(user_query, all_candidates, top_k=settings.TOP_K_RERANK)

        # 4. Build context block with inline source labels
        context_blocks = []
        sources = []

        for i, chunk in enumerate(reranked, 1):
            p = chunk["payload"]
            title = p.get("title", p.get("filename", "Unknown"))
            vendor = p.get("vendor", p.get("source", "Unknown Source"))
            published = p.get("published", "")
            severity = p.get("severity", "")

            source_label = f"[{i}] {vendor} — {title}"
            if published:
                source_label += f" ({published})"
            if severity:
                source_label += f" | Severity: {severity}"

            context_blocks.append(f"### Source {i}: {title}\n{p.get('text', '')}")
            sources.append({
                "id": i,
                "title": title,
                "vendor": vendor,
                "published": published,
                "severity": severity,
                "link": p.get("link", ""),
            })

        context_str = "\n\n".join(context_blocks)

        # 5. Groq prompt with intelligent fallback
        system_prompt = """You are JARVIS — a highly capable IT, Networking, and Security Operations Center (NOC) assistant.

Your job is to answer the user's QUESTION.
You have been provided with CONTEXT from live security feeds.

RULES:
1. If the CONTEXT contains information relevant to the QUESTION (e.g. recent security advisories, CVEs), you MUST use it to answer and cite your sources using [1], [2], etc.
2. If the CONTEXT is irrelevant to the QUESTION (e.g. general IT questions like "How do I configure OSPF?", "Write a script"), completely IGNORE the CONTEXT and answer the QUESTION using your general expert knowledge.
3. Be professional, precise, and concise."""

        user_prompt = f"""CONTEXT:
{context_str}

QUESTION:
{user_query}

Instructions: Evaluate if the CONTEXT is relevant to the QUESTION. If yes, use it and cite sources. If no, ignore the CONTEXT and answer based on your general IT knowledge."""

        groq_response = groq_client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,  # Low temperature = more faithful to context
        )

        answer = groq_response.choices[0].message.content

        return {
            "answer": answer,
            "sources": sources,
            "filters_applied": filters or {},
        }


rag_service = RAGService()

def get_rag_service() -> RAGService:
    return rag_service
