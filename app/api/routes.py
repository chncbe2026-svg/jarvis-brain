"""
JARVIS API Routes — Enhanced
Preserves all existing endpoints while adding:
- Memory CRUD endpoints
- Proactive message endpoint
- Intent inspection endpoint
- Health improvements
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from app.services.rag_service import get_rag_service, RAGService
from app.services.memory_service import memory_service, MemoryType
from app.services.intent_router import detect_intent
from app.services.notification_service import NotificationService
import logging
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Smart Memory File Parser ───────────────────────────────────────────────────

def _parse_memory_file(content: str) -> list[tuple[str, str]]:
    """
    Parses structured memory injection files into (tag, content) pairs.

    Supports two formats:

    Format 1 — [TAG] block style (preferred):
    ─────────────────────────────────────────
        [IDENTITY] Name: Karthikeyan B Role: Executive Director
        [REPORTING STRUCTURE] Dinesh reports directly to Karthikeyan B.

    Format 2 — Plain lines (fallback):
    ─────────────────────────────────────────
        Sir prefers working late at night
        Karthikeyan manages the CHN group

    Returns: list of (tag, content_text) tuples
    """
    import re

    entries = []
    lines = content.splitlines()

    # Detect if file uses [TAG] block format
    has_tags = any(re.match(r'^\[.+?\]', line.strip()) for line in lines)

    if has_tags:
        current_tag = ""
        current_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            tag_match = re.match(r'^\[(.+?)\]\s*(.*)', line)
            if tag_match:
                # Save previous block
                if current_lines:
                    block = " ".join(current_lines).strip()
                    if block:
                        entries.append((current_tag, block))
                current_tag = tag_match.group(1).strip()
                rest = tag_match.group(2).strip()
                current_lines = [rest] if rest else []
            else:
                current_lines.append(line)

        # Save last block
        if current_lines:
            block = " ".join(current_lines).strip()
            if block:
                entries.append((current_tag, block))

    else:
        # Fallback: group by blank-line-separated paragraphs
        paragraph = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                paragraph.append(stripped)
            else:
                if paragraph:
                    entries.append(("fact", " ".join(paragraph)))
                    paragraph = []
        if paragraph:
            entries.append(("fact", " ".join(paragraph)))

    return entries


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

class NotificationTriggerRequest(BaseModel):
    user_name: str
    plan_name: str
    amount: str
    subscription_id: str
    transaction_id: str
    date: str
    email: Optional[str] = None
    telegram: bool = True

class RepeatingNotificationRequest(BaseModel):
    user_name: str
    plan_name: str
    interval_seconds: int
    count: int = 3


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
    """
    Ingest text into JARVIS RAG knowledge base (technical documents).
    ⚠️  This goes into the RAG knowledge base (vendor_news / network_knowledge / personal).
    ⚠️  Only recalled when Sir asks TECHNICAL questions.
    Use /memory/store for personal facts, relationships, and preferences.
    """
    try:
        count = await rag.ingest_text(
            text=request.text,
            metadata=request.metadata or "Manual Ingest",
            collection=request.collection,
        )
        return {
            "status":        "success",
            "chunks_stored": count,
            "destination":   request.collection or "vendor_news (default)",
            "message":       f"Sir, {count} document(s) ingested into the RAG knowledge base.",
        }
    except Exception as e:
        logger.error(f"[API] Ingest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Smart File Upload Endpoint (NEW) ──────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    destination: str = Form(default="memory"),
    memory_type: str = Form(default="fact"),
    importance: float = Form(default=0.8),
    collection: str = Form(default=""),
    rag: RAGService = Depends(get_rag_service),
):
    """
    ═══════════════════════════════════════════════════════════════
    SMART FILE UPLOAD — Choose the correct destination:
    ═══════════════════════════════════════════════════════════════

    destination=memory  →  Stores into jarvis_memory (PERSONAL)
    ─────────────────────────────────────────────────────────────
    Use for:
      • Personal facts about Sir or people he knows
      • Relationships (who is Karthikeyan, who is the manager)
      • Preferences (Sir likes dark mode, works late nights)
      • Goals and plans
    memory_type options: fact | relationship | preference | goal | emotional | reminder
    importance: 0.0 to 1.0 (use 0.9 for important facts)
    Recalled: During EVERY conversation automatically.

    destination=rag  →  Stores into RAG knowledge base (TECHNICAL)
    ─────────────────────────────────────────────────────────────
    Use for:
      • Technical documentation, manuals, SOPs
      • Network diagrams, IT procedures
      • Vendor information, security advisories
    collection options: personal_memory | network_knowledge | vendor_news
    Recalled: Only when Sir asks a TECHNICAL question.
    ═══════════════════════════════════════════════════════════════
    """
    try:
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8", errors="ignore").strip()

        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        filename = file.filename or "uploaded_file.txt"

        # ── Route to MEMORY (personal facts, relationships, etc.) ──
        if destination == "memory":
            entries = _parse_memory_file(content)

            if not entries:
                raise HTTPException(status_code=400, detail="No content found in file.")

            # Map [TAG] names to proper memory_type
            tag_to_type = {
                "IDENTITY":           "fact",
                "SUMMARY":            "fact",
                "SKILLS":             "fact",
                "EXPERIENCE":         "fact",
                "EDUCATION":          "fact",
                "REPORTING STRUCTURE":"relationship",
                "SYSTEM NOTES":       "fact",
                "PREFERENCE":         "preference",
                "GOAL":               "goal",
                "RELATIONSHIP":       "relationship",
                "REMINDER":           "reminder",
                "EMOTIONAL":          "emotional",
            }

            stored = 0
            for tag, block_content in entries:
                resolved_type = tag_to_type.get(tag.upper(), memory_type)
                full_entry = f"[{tag}] {block_content}" if tag else block_content
                success = await memory_service.store(
                    content=full_entry,
                    memory_type=resolved_type,
                    importance=importance,
                    metadata={"source": filename, "tag": tag},
                )
                if success:
                    stored += 1

            return {
                "status":        "success",
                "destination":   "jarvis_memory (personal)",
                "file":          filename,
                "blocks_stored": stored,
                "memory_type":   memory_type,
                "importance":    importance,
                "message":       f"Sir, {stored} memory blocks stored. JARVIS will recall these in every conversation.",

            }

        # ── Route to RAG (technical knowledge base) ──
        elif destination == "rag":
            target_collection = collection or "vendor_news"
            count = await rag.ingest_text(
                text=content,
                metadata={
                    "title":    filename,
                    "filename": filename,
                    "vendor":   "Manual Upload",
                    "text":     content,
                },
                collection=target_collection,
            )
            return {
                "status":        "success",
                "destination":   f"RAG knowledge base → {target_collection}",
                "file":          filename,
                "chunks_stored": count,
                "message":       f"Sir, file ingested into technical knowledge base. Recalled only for technical queries.",
            }

        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid destination. Use 'memory' for personal facts or 'rag' for technical documents."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Upload error: {e}", exc_info=True)
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


# ── Notification Endpoints ────────────────────────────────────────────────────

@router.post("/notifications/trigger")
async def trigger_notification(request: NotificationTriggerRequest):
    """Trigger a one-time subscription notification via Email and Telegram."""
    details = request.dict()
    results = {}
    
    if request.email:
        email_body = NotificationService.get_subscription_email_template(details)
        results["email"] = await NotificationService.send_email(
            to_email=request.email,
            subject=f"Subscription Confirmed: {request.plan_name}",
            body=email_body
        )
        
    if request.telegram:
        telegram_msg = NotificationService.get_subscription_telegram_template(details)
        results["telegram"] = await NotificationService.send_telegram(telegram_msg)
        
    return {
        "status": "completed",
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.post("/notifications/repeating")
async def trigger_repeating_notification(request: RepeatingNotificationRequest, background_tasks: BackgroundTasks):
    """Trigger repeating alerts for a subscription."""
    async def repeat_task(req: RepeatingNotificationRequest):
        for i in range(req.count):
            msg = f"🔔 <b>Repeating Alert ({i+1}/{req.count})</b>\n\nSir, {req.user_name}'s <b>{req.plan_name}</b> subscription requires immediate attention."
            await NotificationService.send_telegram(msg)
            if i < req.count - 1:
                await asyncio.sleep(req.interval_seconds)

    background_tasks.add_task(repeat_task, request)
    return {
        "status": "scheduled", 
        "message": f"Alert will repeat {request.count} times every {request.interval_seconds}s",
        "timestamp": datetime.now(timezone.utc).isoformat()
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

@router.post("/notifications/monthly-trigger/")
async def trigger_monthly_notification():
    """Trigger the monthly service alert email from Apps Script."""
    success = await NotificationService._call_apps_script("triggerEmailAlerts", {})
    if success:
        return {"status": "completed", "message": "Monthly alerts dispatched"}
    raise HTTPException(status_code=500, detail="Failed to trigger monthly alerts")
