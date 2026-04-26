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
    Pure Semantic Search for Maximum Speed. 
    (BM25/Scroll disabled for performance).
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
    
    combined = []
    for hit in semantic_hits:
        combined.append({"id": str(hit.id), "score": hit.score, "payload": hit.payload})

    return combined

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
        print(f"[RAG] Processing Query: {user_query}")
        
        # ─── AUTO-LEARNING LOGIC ───
        # Clean the query (remove "JARVIS, " prefix)
        clean_query = user_query.lower().strip()
        if clean_query.startswith("jarvis"):
            clean_query = clean_query.replace("jarvis", "", 1).strip().lstrip(",").strip()
            
        if any(word in clean_query for word in ["learn", "remember", "memorize", "note down"]):
            print(f"[RAG] Learning intent detected. Ingesting to personal memory...")
            try:
                # Strip the "learn" keyword and store the core fact
                fact = clean_query
                for word in ["learn that", "learn", "remember that", "remember", "memorize", "note down"]:
                    if clean_query.startswith(word):
                        fact = clean_query[len(word):].strip()
                        break
                
                # Use original case for the stored fact if possible
                original_fact = user_query
                if clean_query in user_query.lower():
                    # Try to find the cleaned part in original text to preserve case
                    start_idx = user_query.lower().find(fact)
                    if start_idx != -1:
                        original_fact = user_query[start_idx:].strip()
                else:
                    original_fact = fact # Fallback to cleaned lowercase
                
                metadata = {
                    "source": "manual_voice_learning",
                    "type": "personal_memory",
                    "timestamp": str(uuid.uuid4())
                }
                await self.ingest_text(original_fact, metadata, settings.COLLECTION_PERSONAL)
                
                return {
                    "answer": f"Sir, I've successfully committed that to my central knowledge base. I will remember that: \"{original_fact}\"",
                    "sources": []
                }
            except Exception as e:
                print(f"[RAG] Learning failed: {e}")

        target_collections = [collection] if collection else [
            settings.COLLECTION_PERSONAL,
            settings.COLLECTION_NETWORK,
            settings.COLLECTION_VENDOR,
        ]

        qdrant_filter = build_filter(filters)
        all_candidates = []

        error_msg = None
        for coll in target_collections:
            try:
                hits = hybrid_search(user_query, coll, settings.TOP_K_RETRIEVE, qdrant_filter)
                all_candidates.extend(hits)
            except Exception as e:
                print(f"[RAG] SEARCH ERROR in {coll}: {e}")
                error_msg = str(e)

        if not all_candidates:
            if error_msg:
                return {"answer": f"System Error: {error_msg}", "sources": []}
            return {"answer": "Sir, I have searched the knowledge base but found no relevant information regarding this query. Is there anything else I can assist you with?", "sources": []}

        # Sort by Qdrant Semantic Score and take top K
        all_candidates.sort(key=lambda x: x["score"], reverse=True)
        final_docs = all_candidates[:settings.TOP_K_RERANK]

        print(f"[RAG] Final docs selected: {len(final_docs)}")
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

        print(f"[RAG] Sending to Groq...")
        try:
            response = groq_client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.1
            )
            print(f"[RAG] Groq Success!")
            return {"answer": response.choices[0].message.content, "sources": sources}
        except Exception as e:
            print(f"[RAG] GROQ ERROR: {e}")
            return {"answer": f"Sir, I encountered an error while communicating with Groq: {e}", "sources": sources}

rag_service = RAGService()

def get_rag_service() -> RAGService:
    return rag_service
