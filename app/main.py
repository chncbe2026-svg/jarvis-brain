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
    """
    WebSocket-to-SSH bridge using a real PTY + system ssh client.
    This guarantees a fully interactive terminal with proper escape
    sequences, arrow keys, tab completion, etc.
    """
    await websocket.accept()

    host = (settings.SSH_HOST or "").strip()
    port = settings.SSH_PORT
    user = (settings.SSH_USER or "root").strip()
    password = (settings.SSH_PASSWORD or "").strip()
    key_path = (settings.SSH_PRIVATE_KEY or "").strip()

    if not host:
        await websocket.send_text("\r\n\x1b[31m*** SSH_HOST not configured ***\x1b[0m\r\n")
        await websocket.close(code=1011)
        return

    # Build the ssh command
    ssh_cmd = ["ssh", "-tt",
               "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null",
               "-p", str(port)]

    if key_path and os.path.exists(key_path):
        ssh_cmd += ["-i", key_path]

    ssh_cmd.append(f"{user}@{host}")

    # If password is set and no key, wrap with sshpass
    if password and not (key_path and os.path.exists(key_path)):
        ssh_cmd = ["sshpass", "-p", password] + ssh_cmd

    logger.info("[SSH] Spawning: %s", " ".join(ssh_cmd).replace(password, "***") if password else " ".join(ssh_cmd))

    # Open a real pseudo-terminal
    import pty as pty_module
    import struct
    import fcntl
    import termios

    master_fd, slave_fd = pty_module.openpty()

    # Set terminal size
    winsize = struct.pack("HHHH", 30, 120, 0, 0)
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

    process = await asyncio.create_subprocess_exec(
        *ssh_cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
    )

    os.close(slave_fd)  # Only the master end is used from here

    # Make master_fd non-blocking for asyncio
    import select

    loop = asyncio.get_event_loop()

    logger.info("[SSH] PTY process started (pid=%s)", process.pid)

    async def pty_to_ws():
        """Read from PTY master fd and forward to WebSocket."""
        try:
            while process.returncode is None:
                # Wait for data on the master fd
                await asyncio.sleep(0.01)  # tiny yield to event loop
                r, _, _ = select.select([master_fd], [], [], 0)
                if r:
                    try:
                        data = os.read(master_fd, 4096)
                        if data:
                            await websocket.send_text(data.decode("utf-8", errors="replace"))
                        else:
                            break  # EOF
                    except OSError:
                        break
        except (WebSocketDisconnect, ConnectionError):
            pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("[SSH] pty→ws error: %s", e)

    async def ws_to_pty():
        """Read from WebSocket and write to PTY master fd."""
        try:
            async for msg in websocket.iter_text():
                try:
                    os.write(master_fd, msg.encode("utf-8"))
                except OSError:
                    break
        except (WebSocketDisconnect, ConnectionError):
            pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("[SSH] ws→pty error: %s", e)

    t1 = asyncio.create_task(pty_to_ws())
    t2 = asyncio.create_task(ws_to_pty())

    done, pending = await asyncio.wait(
        [t1, t2], return_when=asyncio.FIRST_COMPLETED
    )

    # Cleanup
    for t in pending:
        t.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    # Kill the SSH process if still running
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass

    try:
        os.close(master_fd)
    except OSError:
        pass

    logger.info("[SSH] Session ended (exit=%s)", process.returncode)

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
