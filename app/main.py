import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncssh

from app.services.rag_service import get_rag_service
from app.services.rss_service import get_rss_service
from app.services.qdrant_client import init_collections, get_qdrant_client
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Request / response models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    message: str
    collection: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None   # e.g. {"vendor": "Cisco", "severity": "Critical"}

class ChatRequest(BaseModel):
    """Backwards-compatible shape for existing Jarvis frontend."""
    message: str
    systemPrompt: Optional[str] = None
    userData: Optional[Dict] = None
    pageContext: Optional[str] = None


# ─── Scheduled RSS sync ──────────────────────────────────────────────────────────

async def scheduled_rss_sync():
    logger.info("[Scheduler] Running scheduled RSS sync…")
    rss = get_rss_service()
    try:
        count = await rss.sync_feeds()
        logger.info(f"[Scheduler] RSS sync complete. New items: {count}")
    except Exception as e:
        logger.error(f"[Scheduler] RSS sync failed: {e}")


# ─── App lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Qdrant collections…")
    init_collections()

    logger.info(f"Starting RSS scheduler (every {settings.RSS_SYNC_INTERVAL_MINS} minutes)…")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_rss_sync,
        "interval",
        minutes=settings.RSS_SYNC_INTERVAL_MINS,
        id="rss_sync",
    )
    scheduler.start()

    # Run one sync immediately on startup in the background
    asyncio.create_task(scheduled_rss_sync())

    yield  # App is running

    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")


# ─── App factory ────────────────────────────────────────────────────────────────

app = FastAPI(title="Jarvis RAG Backend — Professional Edition", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Endpoints ───────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat_compat(req: ChatRequest):
    """
    Backwards-compatible endpoint consumed by the existing Jarvis frontend
    (apiManager.js → callLocalServer → http://localhost:3001/api/chat).

    Wraps the full RAG pipeline and returns { text, model } shape.
    """
    rag = get_rag_service()
    result = await rag.query(req.message)

    # Format sources as a readable footer for the chat bubble
    source_footer = _format_source_footer(result["sources"])
    answer_with_sources = result["answer"]
    if source_footer:
        answer_with_sources += f"\n\n{source_footer}"

    return {"text": answer_with_sources, "model": settings.GROQ_MODEL}


@app.post("/query")
async def query(req: QueryRequest):
    """
    Full RAG query with optional collection targeting and metadata filters.

    Example body:
    {
        "message": "Show critical Cisco advisories",
        "filters": {"vendor": "Cisco", "severity": "Critical", "published_after": "2026-04-01"}
    }
    """
    rag = get_rag_service()
    result = await rag.query(
        user_query=req.message,
        collection=req.collection,
        filters=req.filters,
    )
    return result


@app.get("/news/latest")
async def get_latest_news(
    vendor: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 20,
):
    """
    Return the most recently ingested security news items.
    Optionally filter by vendor or severity query params.
    Example: GET /news/latest?vendor=Cisco&severity=Critical
    """
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

    # Sort by published date descending
    news.sort(key=lambda x: x.get("published", ""), reverse=True)
    return {"news": news, "total": len(news)}


@app.post("/ingest")
async def ingest_document(
    collection: str = Form(...),
    vendor: str = Form("Unknown"),
    severity: str = Form("Informational"),
    text: str = Form(None),
    file: UploadFile = File(None),
):
    """
    Ingest a document (txt, md) or raw text into a named collection.
    Supports metadata: vendor, severity.
    """
    rag = get_rag_service()
    content = text
    filename = "manual_entry"

    if file:
        content = (await file.read()).decode("utf-8")
        filename = file.filename

        return {"status": "error", "detail": "No content provided."}

    metadata = {
        "filename": filename,
        "vendor": vendor,
        "severity": severity,
        "type": "manual_upload",
    }

    num_chunks = await rag.ingest_text(content, metadata, collection)
    return {"status": "success", "collection": collection, "chunks": num_chunks}


@app.post("/rss/sync")
async def manual_rss_sync():
    """Manually trigger an RSS feed sync."""
    rss = get_rss_service()
    count = await rss.sync_feeds()
    return {"status": "success", "items_ingested": count}


@app.get("/health")
async def health():
    return {"status": "healthy", "groq_model": settings.GROQ_MODEL}


@app.websocket("/api/ssh")
async def websocket_ssh(websocket: WebSocket):
    import asyncio
    import json
    import os
    import asyncssh
    from fastapi import WebSocketDisconnect

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

        # IMPORTANT: let remote login shell start naturally
        process = await conn.create_process(
            term_type="xterm",
            term_size=(120, 30)
        )

        await websocket.send_text(
            "\r\n\x1b[32m*** Secure Shell Channel Open ***\x1b[0m\r\n"
        )

        # Nudge prompt to render
        process.stdin.write("\n")

        # -------- SSH -> Browser --------
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

        # -------- Browser -> SSH --------
        async def ws_to_ssh():
            try:
                async for msg in websocket.iter_text():

                    # resize control packet
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

                    # raw keyboard input
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
            await websocket.send_text(
                f"\r\n\x1b[31mSSH Failed: {e}\x1b[0m\r\n"
            )
        except:
            pass

        try:
            await websocket.close()
        except:
            pass


# ─── Helpers ────────────────────────────────────────────────────────────────────

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


def _candidate_ssh_hosts(primary_host: str) -> list[str]:
    hosts = []
    for host in [primary_host, "host.docker.internal", "172.17.0.1"]:
        host = (host or "").strip()
        if host and host not in hosts:
            hosts.append(host)
    return hosts
