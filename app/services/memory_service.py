"""
JARVIS Memory Service
Stores and retrieves personal context, emotional states,
goals, preferences, and conversation summaries via Qdrant.
"""

import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

from app.services.qdrant_client import qdrant
from app.services.embedding_service import embedder
from app.core.config import settings
from qdrant_client.http import models
import logging

logger = logging.getLogger(__name__)


# ── Memory Types ───────────────────────────────────────────────────────────────

class MemoryType:
    PREFERENCE    = "preference"      # Sir likes dark mode, prefers mornings
    GOAL          = "goal"            # Sir wants to launch product by June
    EMOTIONAL     = "emotional"       # Sir felt anxious on 2025-01-10
    RELATIONSHIP  = "relationship"    # Sir's wife is Priya, friend is Arjun
    CONVERSATION  = "conversation"    # Summary of what was discussed
    FACT          = "fact"            # General personal facts about Sir
    REMINDER      = "reminder"        # Things to follow up on


MEMORY_COLLECTION = "jarvis_memory"


# ── Memory Service ─────────────────────────────────────────────────────────────

class MemoryService:
    """
    Manages JARVIS's long-term memory about Dinesh (Sir).
    Uses Qdrant as the vector store for semantic retrieval.
    """

    def __init__(self):
        self._ensure_collection()

    def _ensure_collection(self):
        """Create memory collection if it doesn't exist."""
        try:
            existing = [c.name for c in qdrant.get_collections().collections]
            if MEMORY_COLLECTION not in existing:
                qdrant.create_collection(
                    collection_name=MEMORY_COLLECTION,
                    vectors_config=models.VectorParams(
                        size=settings.EMBEDDING_DIM,
                        distance=models.Distance.COSINE
                    )
                )
                logger.info(f"[Memory] Created collection: {MEMORY_COLLECTION}")
        except Exception as e:
            logger.error(f"[Memory] Collection init error: {e}")

    async def store(
        self,
        content: str,
        memory_type: str = MemoryType.FACT,
        metadata: Optional[Dict] = None,
        importance: float = 0.5,
    ) -> bool:
        """
        Store a memory about Sir.
        
        Args:
            content: The memory text (e.g., "Sir prefers working late nights")
            memory_type: Category from MemoryType
            metadata: Extra fields (tags, source, etc.)
            importance: 0.0 to 1.0 — affects retrieval priority
        """
        try:
            vector = embedder.embed_query(content)
            payload = {
                "content":      content,
                "memory_type":  memory_type,
                "importance":   importance,
                "timestamp":    datetime.now(timezone.utc).isoformat(),
                "metadata":     metadata or {},
            }
            qdrant.upsert(
                collection_name=MEMORY_COLLECTION,
                points=[
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload=payload,
                    )
                ]
            )
            logger.info(f"[Memory] Stored [{memory_type}]: {content[:60]}...")
            return True
        except Exception as e:
            logger.error(f"[Memory] Store error: {e}")
            return False

    async def recall(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        limit: int = 5,
        min_score: float = 0.45,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memories for a given query.
        
        Args:
            query: What to search for
            memory_types: Filter by type (None = all types)
            limit: Max memories to return
            min_score: Minimum similarity threshold
        """
        try:
            vector = embedder.embed_query(query)
            
            # Build optional filter
            qdrant_filter = None
            if memory_types:
                qdrant_filter = models.Filter(
                    must=[
                        models.FieldCondition(
                            key="memory_type",
                            match=models.MatchAny(any=memory_types)
                        )
                    ]
                )

            results = qdrant.query_points(
                collection_name=MEMORY_COLLECTION,
                query=vector,
                limit=limit,
                with_payload=True,
                query_filter=qdrant_filter,
            )

            memories = []
            for hit in results.points:
                if hit.score >= min_score:
                    memories.append({
                        "content":     hit.payload.get("content", ""),
                        "type":        hit.payload.get("memory_type", "fact"),
                        "importance":  hit.payload.get("importance", 0.5),
                        "timestamp":   hit.payload.get("timestamp", ""),
                        "score":       hit.score,
                    })

            # Sort by importance × score for best recall
            memories.sort(
                key=lambda m: m["importance"] * m["score"],
                reverse=True
            )
            return memories

        except Exception as e:
            logger.error(f"[Memory] Recall error: {e}")
            return []

    async def recall_recent_emotional(self, limit: int = 3) -> List[Dict]:
        """Retrieve Sir's recent emotional states for empathetic context."""
        try:
            results = qdrant.scroll(
                collection_name=MEMORY_COLLECTION,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="memory_type",
                            match=models.MatchValue(value=MemoryType.EMOTIONAL)
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            memories = []
            for point in results[0]:
                memories.append({
                    "content":   point.payload.get("content", ""),
                    "timestamp": point.payload.get("timestamp", ""),
                })
            return memories
        except Exception as e:
            logger.error(f"[Memory] Emotional recall error: {e}")
            return []

    async def store_conversation_summary(
        self,
        user_message: str,
        jarvis_response: str,
        intent: str = "unknown"
    ) -> bool:
        """
        Summarize and store conversation turn for future context.
        Stored as lightweight memory — not full transcripts.
        """
        summary = (
            f"Sir said: '{user_message[:120]}' | "
            f"JARVIS responded about: '{jarvis_response[:120]}'"
        )
        return await self.store(
            content=summary,
            memory_type=MemoryType.CONVERSATION,
            metadata={"intent": intent},
            importance=0.3,
        )

    async def get_memory_context_string(
        self,
        query: str,
        limit: int = 4
    ) -> str:
        """
        Returns formatted memory block for injection into prompts.
        """
        memories = await self.recall(query=query, limit=limit)
        if not memories:
            return ""

        lines = ["📌 What I remember about Sir:"]
        for m in memories:
            ts = m["timestamp"][:10] if m["timestamp"] else "sometime"
            lines.append(f"  • [{m['type']} | {ts}] {m['content']}")

        return "\n".join(lines)


memory_service = MemoryService()
