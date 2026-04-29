"""
JARVIS API Routes — Enhanced
Preserves all existing endpoints while adding:
- Memory CRUD endpoints
- Proactive message endpoint
- Intent inspection endpoint
- Health improvements
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from app.services.rag_service import get_rag_service, RAGService
from app.services.memory_service import memory_service, MemoryType
from app.services.intent_router import detect_intent
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response Models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str                              = Field(..., min_length=1, max_length=2000)
    collection:     Optional[str]           = None
    filters:        Optional[Dict]          = None
    history:        Optional[List[Dict]]    = None

class QueryResponse(BaseModel):
    answer:  str
    sources: List[Dict]         = []
    intent:  Optional[str]      = None
    mode:    Optional[str]      = None
    timestamp: str              = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class IngestRequest(BaseModel):
    text:       str
    metadata:   Optional[Dict]  = None
    collection: Optional[str]   = None

class MemoryStoreRequest(BaseModel):
    content:        str
    memory_type:    str     = MemoryType.FACT
    importance:     float   = Field(default=0.5, ge=0.0, le=1.0)
    metadata:       Optional[Dict] = None

class MemoryRecallRequest(BaseModel):
    query:          str
    memory_types:   Optional[List[str]] = None
    limit:          int     = Field(default=5, ge=1, le=20)

class IntentCheckRequest(BaseModel):
    text: str


# ── Core Query Endpoint (Preserved) ───────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query_jarvis(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    rag: RAGService = Depends(get_rag_service),
):
    """
    Main JARVIS query endpoint.
    Automatically routes between companion and technical modes.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty, Sir.")

    try:
        result = await rag.query(
            user_query=request.query,
            collection=request.collection,
            filters=request.filters,
            history=request.history,
        )
        return QueryResponse(**result)
    except Exception as e:
        logger.error(f"[API] Query error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Sir, something went wrong on my end. Investigating."
        )


# ── Ingest Endpoint (Preserved + Enhanced) ────────────────────────────────────

@router.post("/ingest")
async def ingest_document(
    request: IngestRequest,
    rag: RAGService = Depends(get_rag_service),
):
    """Ingest text into JARVIS knowledge base."""
    try:
        count = await rag.ingest_text(
            text=request.text,
            metadata=request.metadata or "Manual Ingest",
            collection=request.collection,
        )
        return {
            "status":        "success",
            "chunks_stored": count,
            "message":       f"Sir, {count} document(s) ingested successfully.",
        }
    except Exception as e:
        logger.error(f"[API] Ingest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Memory Endpoints (NEW) ─────────────────────────────────────────────────────

@router.post("/memory/store")
async def store_memory(request: MemoryStoreRequest):
    """
    Store a personal memory about Sir.
    Use this to teach JARVIS about preferences, goals, relationships.
    """
    success = await memory_service.store(
        content=request.content,
        memory_type=request.memory_type,
        importance=request.importance,
        metadata=request.metadata,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Memory storage failed.")

    return {
        "status":  "stored",
        "content": request.content[:80] + "..." if len(request.content) > 80 else request.content,
        "type":    request.memory_type,
        "message": "Noted and remembered, Sir.",
    }


@router.post("/memory/recall")
async def recall_memory(request: MemoryRecallRequest):
    """
    Retrieve memories relevant to a query.
    Useful for debugging what JARVIS remembers.
    """
    memories = await memory_service.recall(
        query=request.query,
        memory_types=request.memory_types,
        limit=request.limit,
    )
    return {
        "query":    request.query,
        "memories": memories,
        "count":    len(memories),
    }


@router.get("/memory/emotional")
async def get_emotional_history(limit: int = 5):
    """Get Sir's recent emotional history stored by JARVIS."""
    memories = await memory_service.recall_recent_emotional(limit=limit)
    return {"emotional_memories": memories, "count": len(memories)}


# ── Proactive Endpoint (NEW) ───────────────────────────────────────────────────

@router.get("/proactive")
async def get_proactive_message(rag: RAGService = Depends(get_rag_service)):
    """
    Get a proactive check-in message from JARVIS.
    Call this on schedule (cron/scheduler) to simulate JARVIS initiating.
    """
    result = await rag.get_proactive_message()
    return QueryResponse(**result)


# ── Intent Inspector (NEW — Debugging) ────────────────────────────────────────

@router.post("/inspect/intent")
async def inspect_intent(request: IntentCheckRequest):
    """
    Debug endpoint: See how JARVIS classifies a query.
    Useful for tuning intent routing.
    """
    intent, confidence = detect_intent(request.text)
    return {
        "text":       request.text,
        "intent":     str(intent),
        "confidence": round(confidence, 3),
        "will_use_rag":       intent.value in ["technical", "mixed", "memory"],
        "will_use_companion": intent.value in ["emotional", "casual", "greeting", "mixed"],
    }


# ── Health Endpoint (Enhanced) ────────────────────────────────────────────────

@router.get("/health")
async def health_check(rag: RAGService = Depends(get_rag_service)):
    """
    Comprehensive health check for Docker healthcheck and monitoring.
    Returns 200 if all systems operational, 503 if degraded.
    """
    from app.services.qdrant_client import qdrant
    from app.core.config import settings

    status = {
        "status":       "operational",
        "jarvis":       "online",
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "components":   {},
    }
    degraded = False

    # Check Groq keys
    key_count = len(rag.clients)
    status["components"]["groq"] = {
        "status": "ok" if key_count > 0 else "warning",
        "keys_loaded": key_count,
    }
    if key_count == 0:
        degraded = True

    # Check Qdrant
    try:
        collections = qdrant.get_collections()
        coll_names = [c.name for c in collections.collections]
        status["components"]["qdrant"] = {
            "status":      "ok",
            "collections": coll_names,
        }
    except Exception as e:
        status["components"]["qdrant"] = {"status": "error", "detail": str(e)}
        degraded = True

    # Check memory collection
    try:
        from app.services.memory_service import MEMORY_COLLECTION
        mem_ok = MEMORY_COLLECTION in coll_names
        status["components"]["memory"] = {
            "status": "ok" if mem_ok else "initializing",
        }
    except Exception:
        status["components"]["memory"] = {"status": "unknown"}

    if degraded:
        status["status"] = "degraded"
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=status)

    return status
