"""
JARVIS Configuration
Centralized settings with all required constants.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    
    # ── Groq ──────────────────────────────────────────────────────────────────
    GROQ_API_KEY:   str     = ""
    GROQ_KEYS:      str     = ""
    GROQ_MODEL:     str     = "llama-3.3-70b-versatile"
    
    # ── Qdrant ────────────────────────────────────────────────────────────────
    QDRANT_HOST:    str     = "qdrant"
    QDRANT_PORT:    int     = 6333
    QDRANT_URL:     str     = ""
    QDRANT_API_KEY: str     = ""
    EMBEDDING_DIM:  int     = 384
    
    # Local embedding config
    EMBEDDING_MODEL: str = "nomic-ai/nomic-embed-text-v1.5"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ── Collections ───────────────────────────────────────────────────────────
    COLLECTION_PERSONAL:    str = "personal_memory"
    COLLECTION_NETWORK:     str = "network_knowledge"
    COLLECTION_VENDOR:      str = "vendor_news"
    
    # ── JARVIS Identity ────────────────────────────────────────────────────────
    JARVIS_OWNER:   str     = "Dinesh"
    JARVIS_VERSION: str     = "2.0.0"
    
    # ── Memory ────────────────────────────────────────────────────────────────
    MEMORY_COLLECTION:  str     = "jarvis_memory"
    MEMORY_MIN_SCORE:   float   = 0.45
    MEMORY_LIMIT:       int     = 5

    # ── RSS / Background ──────────────────────────────────────────────────────
    RSS_INTERVAL_SECONDS:   int = 3600   # 1 hour
    RSS_TIMEOUT_SECONDS:    int = 30
    
    # ── SSH Variables ─────────────────────────────────────────────────────────
    SSH_HOST: str = "192.168.10.152"
    SSH_PORT: int = 22
    SSH_USER: str = "root"
    SSH_PASSWORD: str = ""
    SSH_PRIVATE_KEY: str = "/app/ssh_key"
    
    # ── Email / Notifications ──────────────────────────────────────────────────
    SMTP_SERVER:    str     = "smtp.gmail.com"
    SMTP_PORT:      int     = 587
    SMTP_USER:      str     = ""
    SMTP_PASSWORD:  str     = ""
    EMAILS_FROM_EMAIL: str  = "notifications@chn.com"
    
    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID:   str = ""
    
    # ── Google Apps Script (Backup / Notification Hub) ────────────────────────
    SHEET_URL: str = "https://script.google.com/macros/s/AKfycbxLohIYNTDJZolRhgWODwtetyCe267EEw5arp829Ls8ehxp4AOa626gl4YkOLAOvy3K/exec"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

def get_settings() -> Settings:
    return settings
