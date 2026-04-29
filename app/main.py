"""
JARVIS FastAPI Application
Production-ready entry point with:
- Proper lifespan management
- Background RSS without blocking
- Graceful error handling
- Preserved legacy endpoints and SSH Websocket
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict

from app.api.routes import router
from app.core.config import settings
from app.services.memory_service import memory_service
from app.services.rag_service import get_rag_service
from app.services.rss_service import get_rss_service

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("jarvis")

class ChatRequest(BaseModel):
    """Backwards-compatible shape for existing Jarvis frontend."""
    message: str
    systemPrompt: Optional[str] = None
    userData: Optional[Dict] = None
    pageContext: Optional[str] = None

# ── Background RSS Task ────────────────────────────────────────────────────────

async def _rss_ingestion_loop():
    """
    Background RSS ingestion loop.
    Runs independently — exceptions never affect API responsiveness.
    Uses non-blocking sleep to prevent event loop starvation.
    """
    from app.services.rag_service import rag_service
    
    # Initial delay to let services warm up
    await asyncio.sleep(10)
    
    while True:
        try:
            logger.info("[RSS] 🔄 Starting ingestion cycle...")
            rss = get_rss_service()
            count = await rss.sync_feeds()
            logger.info(f"[RSS] ✅ Ingestion cycle complete. Items: {count}")
            
        except asyncio.CancelledError:
            logger.info("[RSS] 🛑 Ingestion loop cancelled cleanly")
            break
        except Exception as e:
            # Catch-all: log and continue — never kill the background task
            logger.error(f"[RSS] ❌ Unexpected error in ingestion loop: {e}")
        
        # Non-blocking sleep — won't starve the event loop
        await asyncio.sleep(settings.RSS_INTERVAL_SECONDS)


# ── Application Lifespan ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages startup and shutdown lifecycle.
    Starts background tasks cleanly and cancels them on shutdown.
    """
    logger.info("=" * 60)
    logger.info(f"  JARVIS v{settings.JARVIS_VERSION} — ONLINE")
    logger.info(f"  Loyal companion to {settings.JARVIS_OWNER} (Sir)")
    logger.info("=" * 60)
    
    from app.services.qdrant_client import init_collections
    init_collections()
    
    # Initialize memory collection
    try:
        logger.info("[JARVIS] 🧠 Initializing memory layer...")
        # Memory service init already handles collection creation
        logger.info("[JARVIS] ✅ Memory layer ready")
    except Exception as e:
        logger.error(f"[JARVIS] Memory init warning: {e}")

    # Start background RSS task
    rss_task = asyncio.create_task(
        _rss_ingestion_loop(),
        name="rss-ingestion"
    )
    logger.info("[JARVIS] 📡 RSS ingestion background task started")
    
    yield  # Application runs here
    
    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("[JARVIS] 🛑 Initiating graceful shutdown...")
    rss_task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(rss_task), timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    logger.info("[JARVIS] ✅ Shutdown complete. Goodbye, Sir.")


# ── FastAPI App ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="JARVIS — Personal AI Companion",
    description="Loyal AI companion for Dinesh (Sir). Powered by RAG + Groq + Qdrant.",
    version=settings.JARVIS_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ─────────────────────────────────────────────────────────────────────
app.include_router(router, prefix="/api/v1")


# ── Root ───────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "message": f"JARVIS v{settings.JARVIS_VERSION} online. At your service, Sir.",
        "docs":    "/docs",
        "health":  "/api/v1/health",
    }

@app.get("/health")
async def health_compat():
    """Backwards compatible health check for legacy docker-compose and monitoring."""
    from app.api.routes import health_check
    from app.services.rag_service import get_rag_service
    return await health_check(get_rag_service())


# ── PRESERVED LEGACY ENDPOINTS ─────────────────────────────────────────────────

class LegacyQueryRequest(BaseModel):
    message: str
    collection: Optional[str] = None
    filters: Optional[Dict] = None
    history: Optional[List[Dict]] = None

@app.post("/query")
async def legacy_query(req: LegacyQueryRequest):
    """Backwards compatibility for apiManager.js hitting /query with 'message' instead of 'query'."""
    from app.api.routes import QueryRequest, query_jarvis
    from fastapi import BackgroundTasks
    
    new_req = QueryRequest(
        query=req.message,
        collection=req.collection,
        filters=req.filters,
        history=req.history
    )
    rag = get_rag_service()
    # Execute query_jarvis but extract just the dictionary to return directly
    result = await rag.query(
        user_query=new_req.query,
        collection=new_req.collection,
        filters=new_req.filters,
        history=new_req.history
    )
    return result

@app.post("/ingest")
async def legacy_ingest(
    collection: str = Form(...),
    vendor: str = Form("Unknown"),
    severity: str = Form("Informational"),
    text: str = Form(None),
    file: UploadFile = File(None),
):
    """Backwards compatibility for apiManager.js sending FormData to /ingest."""
    rag = get_rag_service()
    content = text
    filename = "manual_entry"

    if file:
        content = (await file.read()).decode("utf-8")
        filename = file.filename

    if not content:
        return {"status": "error", "detail": "No content provided."}

    metadata = {
        "filename": filename,
        "vendor": vendor,
        "severity": severity,
        "type": "manual_upload",
    }

    num_chunks = await rag.ingest_text(content, metadata, collection)
    return {"status": "success", "collection": collection, "chunks": num_chunks}

@app.post("/api/chat")
async def chat_compat(req: ChatRequest):
    rag = get_rag_service()
    result = await rag.query(req.message)

    # Format sources as a readable footer for the chat bubble
    sources = result.get("sources", [])
    source_footer = _format_source_footer(sources)
    answer_with_sources = result["answer"]
    if source_footer:
        answer_with_sources += f"\n\n{source_footer}"

    return {"text": answer_with_sources, "model": settings.GROQ_MODEL}

@app.get("/news/latest")
async def get_latest_news(
    vendor: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 20,
):
    from app.services.qdrant_client import get_qdrant_client
    qdrant = get_qdrant_client()
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue

    conditions = []
    if vendor:
        conditions.append(FieldCondition(key="vendor", match=MatchValue(value=vendor)))
    if severity:
        conditions.append(FieldCondition(key="severity", match=MatchValue(value=severity)))

    scroll_filter = Filter(must=conditions) if conditions else None

    results, _ = qdrant.scroll(
        collection_name=settings.COLLECTION_VENDOR,
        scroll_filter=scroll_filter,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    news = []
    for r in results:
        p = r.payload
        news.append({
            "title": p.get("title", ""),
            "vendor": p.get("vendor", ""),
            "severity": p.get("severity", ""),
            "published": p.get("published", ""),
            "link": p.get("link", ""),
            "feed_type": p.get("feed_type", ""),
        })

    news.sort(key=lambda x: x.get("published", ""), reverse=True)
    return {"news": news, "total": len(news)}

@app.post("/rss/sync")
async def manual_rss_sync():
    rss = get_rss_service()
    count = await rss.sync_feeds()
    return {"status": "success", "items_ingested": count}

@app.websocket("/api/ssh")
async def websocket_ssh(websocket: WebSocket):
    import json
    import os
    import asyncssh

    await websocket.accept()
    logger.info("[SSH] Starting browser terminal session")

    try:
        key_path = (settings.SSH_PRIVATE_KEY or "").strip()
        client_keys = [key_path] if key_path and os.path.isfile(key_path) else None

        conn = await asyncssh.connect(
            host=settings.SSH_HOST,
            port=settings.SSH_PORT,
            username=settings.SSH_USER,
            password=settings.SSH_PASSWORD or None,
            client_keys=client_keys,
            known_hosts=None
        )

        logger.info("[SSH] Connected")

        process = await conn.create_process(
            term_type="xterm",
            term_size=(120, 30)
        )

        await websocket.send_text(
            "\r\n\x1b[32m*** Secure Shell Channel Open ***\x1b[0m\r\n"
        )

        process.stdin.write("\n")

        async def ssh_to_ws():
            try:
                while True:
                    chunk = await process.stdout.read(1024)
                    if not chunk:
                        break
                    await websocket.send_text(chunk)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"[SSH OUT ERROR] {e}")

        async def ws_to_ssh():
            try:
                async for msg in websocket.iter_text():
                    if msg.startswith("{"):
                        try:
                            ctrl = json.loads(msg)
                            if ctrl.get("type") == "resize":
                                process.change_terminal_size(
                                    int(ctrl["cols"]),
                                    int(ctrl["rows"])
                                )
                                continue
                        except Exception:
                            pass
                    process.stdin.write(msg)
            except WebSocketDisconnect:
                pass
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"[SSH IN ERROR] {e}")

        t1 = asyncio.create_task(ssh_to_ws())
        t2 = asyncio.create_task(ws_to_ssh())

        done, pending = await asyncio.wait(
            [t1, t2],
            return_when=asyncio.FIRST_COMPLETED
        )

        for t in pending:
            t.cancel()

        await asyncio.gather(*pending, return_exceptions=True)

        try:
            process.terminate()
        except:
            pass

        conn.close()
        logger.info("[SSH] Session closed")

    except Exception as e:
        logger.exception("[SSH FATAL]")
        try:
            await websocket.send_text(f"\r\n\x1b[31mSSH Failed: {e}\x1b[0m\r\n")
        except:
            pass
        try:
            await websocket.close()
        except:
            pass

def _format_source_footer(sources: list) -> str:
    if not sources:
        return ""
    lines = ["---", "**Sources:**"]
    for s in sources:
        line = f"[{s['id']}] **{s['vendor']}** — {s['title']}"
        if s.get("published"):
            line += f" ({s['published']})"
        if s.get("severity") and s["severity"] != "Informational":
            line += f" | ⚠️ {s['severity']}"
        if s.get("link"):
            line += f" — [link]({s['link']})"
        lines.append(line)
    return "\n".join(lines)
