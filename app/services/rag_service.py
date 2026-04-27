import uuid
import random
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
    def __init__(self):
        self.clients = []
        self._refresh_clients()

    def _refresh_clients(self):
        """Initialize Groq clients from the rotation list."""
        keys = settings.groq_keys_list
        self.clients = [Groq(api_key=key) for key in keys]
        if not self.clients and settings.GROQ_API_KEY:
            self.clients = [Groq(api_key=settings.GROQ_API_KEY)]
        
        logger.info(f"Initialized {len(self.clients)} Groq clients for rotation.")

    def _get_client(self) -> Groq:
        """Get a random client from the pool."""
        if not self.clients:
            return Groq(api_key=settings.GROQ_API_KEY)
        return random.choice(self.clients)

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
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        print(f"[RAG] Processing Query: {user_query}")
        
        # ─── AUTO-LEARNING LOGIC ───
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
                
                # Context Awareness: If fact uses pronouns, try to resolve from history
                subject = None
                if history and len(history) > 0:
                    # Get last user message that wasn't a learn command
                    last_user_msg = None
                    for msg in reversed(history):
                        if msg.get("role") == "user" and not any(w in msg.get("content", "").lower() for w in ["learn", "remember"]):
                            last_user_msg = msg.get("content", "")
                            break
                    
                    if last_user_msg:
                        # Simple heuristic: if learn fact starts with "he", "she", "it", or "they"
                        if any(fact.startswith(p) for p in ["he is", "she is", "it is", "they are", "he ", "she ", "it "]):
                            subject = last_user_msg.strip().capitalize()
                            print(f"[RAG] Resolved pronoun subject from history: {subject}")
                
                # Construct final fact for storage
                stored_fact = fact
                if subject:
                    # Replace "he is" with "Subject is"
                    for p in ["he is", "she is", "it is"]:
                        if fact.startswith(p):
                            stored_fact = fact.replace(p, f"{subject} is", 1)
                            break
                    else:
                        # Fallback: prepend subject
                        stored_fact = f"{subject}: {fact}"
                
                metadata = {
                    "source": "manual_voice_learning",
                    "type": "personal_memory",
                    "timestamp": str(uuid.uuid4()),
                    "original_query": user_query
                }
                await self.ingest_text(stored_fact, metadata, settings.COLLECTION_PERSONAL)
                
                return {
                    "answer": f"Sir, I've successfully committed that to my central knowledge base. I will remember that: \"{stored_fact}\"",
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
            title = p.get("title", "System Info")
            vendor = p.get("vendor", "Internal")
            context_blocks.append(f"### Source {i}: {title}\n{p.get('text', '')}")
            sources.append({
                "id": i, "title": title, "vendor": vendor, 
                "severity": p.get("severity", ""), "link": p.get("link", "")
            })

        context_str = "\n\n".join(context_blocks)
        
        system_prompt = """You are JARVIS — an ultra-intelligent, loyal, and slightly witty AI assistant built by Dinesh (Sir).
You have access to a memory database (CONTEXT), but you must NEVER say "Based on the context". 
CRITICAL RULES:
1. BE CRISP AND CONCISE. 
2. Speak naturally, sharply, and confidently.
3. Your tone must be dry British wit (Paul Bettany style). 
4. If the user asks about a person or fact you just learned, answer directly using the provided context."""

        user_prompt = f"CONTEXT:\n{context_str}\n\nQUESTION:\n{user_query}"

        # ─── ROTATION WITH RETRY LOGIC ───
        max_retries = min(len(self.clients), 3)
        last_error = None

        for attempt in range(max_retries):
            client = self._get_client()
            print(f"[RAG] Sending to Groq (Attempt {attempt+1}/{max_retries})...")
            try:
                response = client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    temperature=0.4
                )
                print(f"[RAG] Groq Success!")
                return {"answer": response.choices[0].message.content, "sources": sources}
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                print(f"[RAG] GROQ ATTEMPT {attempt+1} FAILED: {e}")
                
                # If it's an invalid key or rate limit, we should ideally remove it from pool for this session
                if "invalid api key" in error_str or "401" in error_str or "rate_limit_exceeded" in error_str or "429" in error_str:
                    if client in self.clients:
                        print(f"[RAG] Removing problematic key from current pool.")
                        self.clients.remove(client)
                
                if not self.clients:
                    break

        return {"answer": f"Sir, I've exhausted all available API keys or encountered a persistent error: {last_error}", "sources": sources}

rag_service = RAGService()

def get_rag_service() -> RAGService:
    return rag_service
