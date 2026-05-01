"""
JARVIS RAG Service — Enhanced with Dual-Mode Intelligence
Handles technical RAG queries AND companion-mode conversations.
Preserves all existing functionality while adding:
- Intent routing
- Memory integration
- Companion mode
- Shortcut bypass
- Conversation storage
"""

import uuid
import random
import os
from typing import List, Optional, Dict, Any

from groq import Groq
from app.core.config import settings
from app.services.qdrant_client import qdrant
from app.services.embedding_service import embedder
from app.services.intent_router import detect_intent, should_use_rag, should_use_companion, IntentType
from app.services.memory_service import memory_service, MemoryType
from app.services.companion_service import companion_service
from app.services.shortcut_service import get_shortcut_response
from app.services.web_search_service import (
    web_search, format_results_for_llm, is_web_search_query, extract_search_query
)
from qdrant_client.http import models
import logging

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(self):
        self.clients: List[Groq] = []
        self._refresh_clients()

    # ── Client Management ──────────────────────────────────────────────────────

    def _refresh_clients(self):
        """Load all Groq API keys with visual confirmation."""
        raw_keys = os.getenv("GROQ_KEYS", os.getenv("GROQ_API_KEY", ""))
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        self.clients = [Groq(api_key=k) for k in keys]
        print(f"[JARVIS] ✅ Loaded {len(self.clients)} Groq API key(s).")

    def _get_client(self) -> Groq:
        """Get a random available Groq client."""
        if not self.clients:
            return Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        return random.choice(self.clients)

    # ── LLM Call with Rotation ─────────────────────────────────────────────────

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
    ) -> Optional[str]:
        """
        Call Groq LLM with automatic key rotation and retry.
        Returns response text or None on complete failure.
        """
        active_pool = list(self.clients)
        max_retries = max(len(active_pool), 1)
        
        # Fallback if no clients configured
        if not active_pool:
            fallback = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
            active_pool = [fallback]

        for attempt in range(max_retries):
            if not active_pool:
                break
                
            client = random.choice(active_pool)
            
            # Safe index lookup (fallback client may not be in self.clients)
            try:
                key_idx = self.clients.index(client)
            except ValueError:
                key_idx = 0

            logger.info(f"[LLM] 🔄 Key #{key_idx} | Attempt {attempt+1}/{max_retries}")
            
            try:
                response = client.chat.completions.create(
                    model=settings.GROQ_MODEL,
                    messages=[
                        {"role": "system",  "content": system_prompt},
                        {"role": "user",    "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=1024,
                )
                text = response.choices[0].message.content
                logger.info(f"[LLM] ✅ Success with Key #{key_idx}")
                return text
                
            except Exception as e:
                logger.warning(f"[LLM] ❌ Key #{key_idx} failed: {e}")
                if client in active_pool:
                    active_pool.remove(client)

        return None

    # ── RAG Retrieval ──────────────────────────────────────────────────────────

    def _retrieve_documents(
        self,
        query: str,
        collection: Optional[str] = None,
        limit: int = 5,
    ) -> tuple[List[Dict], List[Dict]]:
        """
        Retrieve relevant documents from Qdrant.
        Returns (context_blocks, sources).
        """
        target_collections = [collection] if collection else [
            settings.COLLECTION_PERSONAL,
            settings.COLLECTION_NETWORK,
            settings.COLLECTION_VENDOR,
        ]

        all_candidates = []
        query_vector = embedder.embed_query(query)

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
                logger.warning(f"[RAG] Search error in '{coll}': {e}")

        # Sort by score, take top results
        all_candidates.sort(key=lambda x: x.score, reverse=True)
        final_docs = all_candidates[:limit]

        context_blocks = []
        sources = []
        for i, doc in enumerate(final_docs, 1):
            p = doc.payload
            context_blocks.append(
                f"### Source {i}: {p.get('title', 'Info')}\n{p.get('text', '')}"
            )
            sources.append({
                "id":     i,
                "title":  p.get("title", "Info"),
                "vendor": p.get("vendor", "System"),
                "score":  round(doc.score, 3),
            })

        return context_blocks, sources

    # ── Main Query Handler ─────────────────────────────────────────────────────

    async def query(
        self,
        user_query: str,
        collection: Optional[str] = None,
        filters: Optional[Dict] = None,
        history: Optional[List] = None,
    ) -> Dict[str, Any]:
        """
        Main JARVIS query handler with full dual-mode intelligence.
        
        Flow:
        1. Check shortcut patterns (greetings, thanks, etc.)
        2. Detect intent (emotional, technical, casual, mixed)
        3. Retrieve memory context
        4. Route to appropriate mode
        5. Call LLM with enriched prompt
        6. Store conversation memory
        7. Return structured response
        """
        logger.info(f"[JARVIS] 💬 Query: {user_query[:80]}...")

        # ── Step 0: Web Search Detection (before any other routing) ──────────
        if is_web_search_query(user_query):
            return await self._handle_web_search(
                user_query=user_query,
            )

        # ── Step 1: Shortcut Check (fastest path) ────────────────────────────
        shortcut = get_shortcut_response(user_query)
        if shortcut:
            logger.info("[JARVIS] ⚡ Shortcut response triggered")
            # Still store this interaction as memory
            await memory_service.store_conversation_summary(
                user_message=user_query,
                jarvis_response=shortcut,
                intent="greeting"
            )
            return {
                "answer":  shortcut,
                "sources": [],
                "intent":  "greeting",
                "mode":    "shortcut",
            }

        # ── Step 2: Intent Detection ─────────────────────────────────────────
        intent, confidence = detect_intent(user_query)
        logger.info(f"[JARVIS] 🧠 Intent: {intent} (confidence: {confidence:.2f})")

        # ── Step 3: Retrieve Memory Context ─────────────────────────────────
        memory_context = await memory_service.get_memory_context_string(
            query=user_query,
            limit=4,
        )

        # ── Step 4: Route by Intent ──────────────────────────────────────────
        
        # --- EMOTIONAL / CASUAL / COMPANION MODE ---
        if intent in {IntentType.EMOTIONAL, IntentType.CASUAL, IntentType.GREETING}:
            return await self._handle_companion_mode(
                user_query=user_query,
                intent=intent,
                memory_context=memory_context,
            )

        # --- MEMORY QUERY MODE ---
        if intent == IntentType.MEMORY:
            return await self._handle_memory_query(
                user_query=user_query,
                memory_context=memory_context,
            )

        # --- MIXED MODE (emotional + technical) ---
        if intent == IntentType.MIXED:
            return await self._handle_mixed_mode(
                user_query=user_query,
                collection=collection,
                memory_context=memory_context,
            )

        # --- TECHNICAL MODE (default RAG) ---
        return await self._handle_technical_mode(
            user_query=user_query,
            collection=collection,
            memory_context=memory_context,
        )

    # ── Mode Handlers ──────────────────────────────────────────────────────────

    async def _handle_companion_mode(
        self,
        user_query: str,
        intent: IntentType,
        memory_context: str = "",
    ) -> Dict[str, Any]:
        """Handle emotional/casual companion conversations without RAG."""
        
        # Detect specific emotional need
        emotional_need = await companion_service.detect_emotional_need(user_query)
        
        # Get recent emotional history for empathy
        recent_emotional = []
        if emotional_need == "emotional":
            recent_emotional = await memory_service.recall_recent_emotional(limit=3)
            # Store this emotional state
            await companion_service.store_emotional_memory(user_query, emotional_need)

        # Build companion system prompt
        system_prompt = companion_service.build_companion_prompt(
            intent=emotional_need,
            memory_context=memory_context,
            recent_emotional=recent_emotional,
        )

        # Call LLM with higher temperature for natural conversation
        response_text = self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_query,
            temperature=0.75,
        )

        if not response_text:
            response_text = (
                "Sir, I'm here. Something's off on my end right now, "
                "but I'm listening. What's going on?"
            )

        # Store conversation memory
        await memory_service.store_conversation_summary(
            user_message=user_query,
            jarvis_response=response_text,
            intent=str(intent),
        )

        return {
            "answer":  response_text,
            "sources": [],
            "intent":  str(intent),
            "mode":    "companion",
        }

    async def _handle_technical_mode(
        self,
        user_query: str,
        collection: Optional[str] = None,
        memory_context: str = "",
    ) -> Dict[str, Any]:
        """Handle technical questions with full RAG pipeline."""
        
        # Retrieve documents
        context_blocks, sources = self._retrieve_documents(
            query=user_query,
            collection=collection,
        )
        context_str = "\n\n".join(context_blocks) if context_blocks else "No relevant documents found."

        # Build technical prompt
        system_prompt = companion_service.build_technical_prompt(
            memory_context=memory_context,
        )

        user_prompt = (
            f"CONTEXT FROM KNOWLEDGE BASE:\n{context_str}\n\n"
            f"Sir's Question: {user_query}"
        )

        # Call LLM with lower temperature for accuracy
        response_text = self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.35,
        )

        if not response_text:
            response_text = (
                "Sir, my language systems hit a snag. "
                "The knowledge base has relevant info — want me to try again?"
            )

        # Store conversation
        await memory_service.store_conversation_summary(
            user_message=user_query,
            jarvis_response=response_text,
            intent="technical",
        )

        return {
            "answer":  response_text,
            "sources": sources,
            "intent":  "technical",
            "mode":    "rag",
        }

    async def _handle_web_search(
        self,
        user_query: str,
    ) -> Dict[str, Any]:
        """
        Handle web search requests.
        1. Extract clean search terms from the query
        2. Fetch real results from DuckDuckGo
        3. Feed results to LLM for a JARVIS-style summarized answer
        4. Auto-store findings into JARVIS memory so he "learns"
        """
        logger.info(f"[WebSearch] 🌐 Web search triggered: {user_query}")

        # Extract clean search query
        search_terms = extract_search_query(user_query)
        logger.info(f"[WebSearch] 🔍 Searching for: '{search_terms}'")

        # Fetch results
        results = await web_search(search_terms, max_results=5)
        context = format_results_for_llm(results, search_terms)

        # Build system prompt for summarization
        system_prompt = """You are JARVIS — inspired by the JARVIS from Iron Man.
You just fetched live web results for Sir. Your job is to:
1. Summarize the most useful information from the search results in a crisp, natural way.
2. Sound like a well-informed companion sharing what you found — not a search engine dumping links.
3. If you found company info, people, or facts — present them clearly.
4. Keep it concise. 3-5 sentences max for casual queries. More detail only if genuinely needed.
5. If results are thin or unclear, say so honestly and share what little you found.
6. NEVER start with "Certainly!" or "Of course!" or robotic openers.
7. End naturally — mention that you've stored this for future reference if relevant."""

        user_prompt = (
            f"Sir asked: \"{user_query}\"\n\n"
            f"Here are the live web results I found:\n\n{context}\n\n"
            f"Please summarize the key findings for Sir in your natural JARVIS style."
        )

        response_text = self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.5,
        )

        if not response_text:
            if results:
                # Fallback: format results directly without LLM
                snippets = "\n".join([f"• **{r['title']}**: {r['snippet'][:120]}" for r in results[:3]])
                response_text = f"Here's what I found about **{search_terms}**, Sir:\n\n{snippets}"
            else:
                response_text = f"I searched the web for **{search_terms}** but couldn't find useful results, Sir. Try a more specific search term."

        # Auto-store findings into memory so JARVIS "learns" from this search
        if results:
            summary_for_memory = f"Web search about '{search_terms}': {results[0].get('snippet', '')[:300]}"
            await memory_service.store(
                content=summary_for_memory,
                memory_type=MemoryType.FACT,
                importance=0.6,
                metadata={"source": "web_search", "query": search_terms},
            )
            logger.info(f"[WebSearch] 🧠 Stored web findings into JARVIS memory")

        # Store conversation
        await memory_service.store_conversation_summary(
            user_message=user_query,
            jarvis_response=response_text,
            intent="web_search",
        )

        # Format sources for the response
        search_sources = [
            {"id": i+1, "title": r["title"], "vendor": r["url"], "score": 1.0}
            for i, r in enumerate(results[:3])
        ]

        return {
            "answer":  response_text,
            "sources": search_sources,
            "intent":  "web_search",
            "mode":    "web_search",
        }

    async def _handle_memory_query(
        self,
        user_query: str,
        memory_context: str = "",
    ) -> Dict[str, Any]:
        """Handle queries about past conversations and preferences."""
        
        # Deep memory search
        memories = await memory_service.recall(
            query=user_query,
            limit=6,
            min_score=0.35,
        )

        memory_block = ""
        if memories:
            lines = ["Here's what I remember:"]
            for m in memories:
                ts = m["timestamp"][:10] if m["timestamp"] else "sometime"
                lines.append(f"  • [{m['type']} | {ts}] {m['content']}")
            memory_block = "\n".join(lines)
        else:
            memory_block = "I don't have specific memories about that yet, Sir."

        system_prompt = companion_service.build_companion_prompt(
            intent="casual",
            memory_context=memory_context,
        )

        user_prompt = (
            f"Sir asked: '{user_query}'\n\n"
            f"MEMORY RETRIEVAL RESULTS:\n{memory_block}\n\n"
            f"Respond naturally based on what you remember. "
            f"If memories are limited, be honest but warm about it."
        )

        response_text = self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.5,
        )

        if not response_text:
            response_text = memory_block

        return {
            "answer":  response_text,
            "sources": [],
            "intent":  "memory",
            "mode":    "memory",
        }

    async def _handle_mixed_mode(
        self,
        user_query: str,
        collection: Optional[str] = None,
        memory_context: str = "",
    ) -> Dict[str, Any]:
        """
        Handle mixed emotional+technical queries.
        Leads with empathy, then addresses the technical need.
        """
        # Get both RAG context and emotional context
        context_blocks, sources = self._retrieve_documents(
            query=user_query,
            collection=collection,
            limit=3,
        )
        context_str = "\n\n".join(context_blocks) if context_blocks else ""

        # Store emotional component
        await companion_service.store_emotional_memory(user_query, "mixed")

        # Build mixed prompt — emotional tone, technical content
        system_prompt = companion_service.build_companion_prompt(
            intent="emotional",
            memory_context=memory_context,
        ) + """

ADDITIONAL INSTRUCTION FOR MIXED MODE:
Sir's message has both an emotional and technical component.
1. First acknowledge the emotional side briefly and warmly
2. Then address the technical question using the provided context
3. End with a caring check-in
"""

        user_prompt = (
            f"Sir said: '{user_query}'\n\n"
            f"RELEVANT KNOWLEDGE BASE CONTEXT:\n{context_str}"
            if context_str else
            f"Sir said: '{user_query}'"
        )

        response_text = self._call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.6,
        )

        if not response_text:
            response_text = "Sir, I hear you. Let me look into that for you."

        await memory_service.store_conversation_summary(
            user_message=user_query,
            jarvis_response=response_text,
            intent="mixed",
        )

        return {
            "answer":  response_text,
            "sources": sources,
            "intent":  "mixed",
            "mode":    "mixed",
        }

    # ── Ingestion (Preserved) ──────────────────────────────────────────────────

    async def ingest_text(
        self,
        text: str,
        metadata: Any = "RSS Feed",
        collection: Optional[str] = None,
    ) -> int:
        """
        Ingest text into Qdrant knowledge base.
        Preserved from original implementation.
        """
        try:
            collection = collection or settings.COLLECTION_VENDOR
            vector = embedder.embed_query(text)

            if isinstance(metadata, dict):
                payload = {**metadata, "text": text}
            else:
                payload = {
                    "title":  str(metadata),
                    "text":   text,
                    "vendor": "RSS",
                }

            qdrant.upsert(
                collection_name=collection,
                points=[
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload=payload,
                    )
                ]
            )

            title = payload.get("title") or payload.get("filename") or "Unknown"
            logger.info(f"[RAG] 📥 Ingested: {title}")
            return 1

        except Exception as e:
            logger.error(f"[RAG] ingest_text error: {e}")
            return 0

    # ── Memory API (Public Interface) ──────────────────────────────────────────

    async def store_memory(
        self,
        content: str,
        memory_type: str = MemoryType.FACT,
        importance: float = 0.5,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Public interface to store personal memories about Sir."""
        return await memory_service.store(
            content=content,
            memory_type=memory_type,
            importance=importance,
            metadata=metadata or {},
        )

    async def get_proactive_message(self) -> Dict[str, Any]:
        """Generate a proactive wellness check-in message."""
        message = companion_service.get_proactive_message()
        return {
            "answer":  message,
            "sources": [],
            "intent":  "proactive",
            "mode":    "companion",
        }


# ── Singleton ──────────────────────────────────────────────────────────────────
rag_service = RAGService()
def get_rag_service() -> RAGService:
    return rag_service
