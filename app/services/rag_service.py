import uuid
import random
import os
from typing import List, Optional, Dict, Any
from groq import Groq
from app.core.config import settings
from app.services.qdrant_client import qdrant
from app.services.embedding_service import embedder
from qdrant_client.http import models
import logging

logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self):
        self.clients = []
        self._refresh_clients()

    def _refresh_clients(self):
        # Directly read from environment to ensure parity with Docker ENV
        raw_keys = os.getenv("GROQ_KEYS", os.getenv("GROQ_API_KEY", ""))
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        self.clients = [Groq(api_key=k) for k in keys]
        print(f"[INIT] Loaded {len(self.clients)} Groq keys.")

    def _get_client(self) -> Groq:
        if not self.clients:
            return Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        return random.choice(self.clients)

    async def query(self, user_query: str, collection=None, filters=None, history=None) -> Dict[str, Any]:
        print(f"[RAG] Processing Query: {user_query}")
        
        # 1. Search Knowledge Base
        target_collections = [collection] if collection else [
            settings.COLLECTION_PERSONAL,
            settings.COLLECTION_NETWORK,
            settings.COLLECTION_VENDOR,
        ]
        
        all_candidates = []
        query_vector = embedder.embed_query(user_query)
        
        for coll in target_collections:
            try:
                search_response = qdrant.query_points(
                    collection_name=coll,
                    query=query_vector,
                    limit=10,
                    with_payload=True,
                )
                for hit in search_response.points:
                    all_candidates.append(hit)
            except Exception as e:
                print(f"[RAG] Search error in {coll}: {e}")

        # Sort and take top matches
        all_candidates.sort(key=lambda x: x.score, reverse=True)
        final_docs = all_candidates[:5]
        
        context_blocks = []
        sources = []
        for i, doc in enumerate(final_docs, 1):
            p = doc.payload
            context_blocks.append(f"### Source {i}: {p.get('title', 'Info')}\n{p.get('text', '')}")
            sources.append({"id": i, "title": p.get('title', 'Info'), "vendor": p.get('vendor', 'System')})

        context_str = "\n\n".join(context_blocks)
        
        system_prompt = """You are JARVIS — an ultra-intelligent AI built by Dinesh (Sir).
Use the provided CONTEXT to answer. Speak with dry British wit. Be concise. 
If the info isn't there, say you don't know."""
        user_prompt = f"CONTEXT:\n{context_str}\n\nQUESTION:\n{user_query}"

        # 2. Call Groq with AUTO-RETRY and VISUAL ROTATION
        active_pool = list(self.clients)
        max_retries = len(active_pool) if active_pool else 1
        last_error = "No keys configured"
        
        for attempt in range(max_retries):
            if not active_pool: break
            client = random.choice(active_pool)
            key_idx = self.clients.index(client)
            
            print(f"[RAG] 🔄 Attempting with Key #{key_idx} (Attempt {attempt+1}/{max_retries})...")
            try:
                response = client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    temperature=0.4
                )
                print(f"[RAG] ✅ SUCCESS using Key #{key_idx}")
                return {"answer": response.choices[0].message.content, "sources": sources}
            except Exception as e:
                print(f"[RAG] ❌ Key #{key_idx} failed. Error: {e}")
                last_error = str(e)
                if client in active_pool: active_pool.remove(client)

        return {"answer": f"Sir, all API keys failed. Last error: {last_error}", "sources": sources}

    async def ingest_text(self, text: str, metadata: Any = "RSS Feed", collection: str = None):
        try:
            collection = collection or settings.COLLECTION_VENDOR
            vector = embedder.embed_query(text)
            
            # Prepare payload
            if isinstance(metadata, dict):
                payload = {**metadata, "text": text}
            else:
                payload = {
                    "title": str(metadata),
                    "text": text,
                    "vendor": "RSS"
                }

            qdrant.upsert(
                collection_name=collection,
                points=[
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload=payload
                    )
                ]
            )

            title = payload.get("title") or payload.get("filename") or "Unknown"
            print(f"[RAG] Ingested: {title}")
            return 1 # Returns 1 chunk ingested

        except Exception as e:
            print(f"[RAG] ingest_text error: {e}")
            return 0

rag_service = RAGService()
def get_rag_service(): return rag_service
