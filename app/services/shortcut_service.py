"""
JARVIS Shortcut Service - Natural, short, human responses
"""

import re
import random
from datetime import datetime, timezone
from typing import Optional


# ── Response Banks — SHORT AND HUMAN ──────────────────────────────────────────

HELLO = [
    "Hey Sir. What's up?",
    "Sir. What do you need?",
    "Here. What's going on?",
    "Hey. What can I do for you?",
]

GOOD_MORNING = [
    "Morning, Sir. How's it looking today?",
    "Good morning. What's first on the list?",
    "Morning. Sleep well?",
    "Morning, Sir. Ready when you are.",
]

GOOD_EVENING = [
    "Evening, Sir. How'd the day go?",
    "Evening. Still going or winding down?",
    "Hey Sir. Long day?",
]

GOOD_NIGHT = [
    "Night, Sir. Rest well.",
    "Good night. You've earned it.",
    "Night. I'll be here.",
    "Sleep well, Sir.",
]

THANKS = [
    "Always, Sir.",
    "Anytime.",
    "That's what I'm here for.",
    "No problem at all.",
]

GOODBYE = [
    "Take care, Sir.",
    "See you soon.",
    "Later, Sir.",
    "I'll be here when you're back.",
]

HOW_ARE_YOU = [
    "Doing well. More importantly — how are you, Sir?",
    "Sharp as ever. You?",
    "All good here. What's up with you?",
]

WAKE_UP = [
    "Online, Sir. What do you need?",
    "Right here. Go ahead.",
    "At your service. What's happening?",
]

ABOUT_ME = [
    "I'm JARVIS — your AI. Built to help you think, build, and get things done. What do you need?",
    "Your personal AI, Sir. Here to help with tech, questions, or just to talk. What's up?",
    "JARVIS. Dinesh's AI companion. Ask me anything.",
]


# ── Rules ──────────────────────────────────────────────────────────────────────

RULES = [
    (r"^(wake up|jarvis|hey jarvis|activate)\b",             WAKE_UP),
    (r"^good\s?morning\b",                                   GOOD_MORNING),
    (r"^good\s?evening\b",                                   GOOD_EVENING),
    (r"^good\s?(night|nite)\b",                              GOOD_NIGHT),
    (r"^(gn|g\.n\.)\b",                                      GOOD_NIGHT),
    (r"^(bye|goodbye|see you|later|take care)\b",            GOODBYE),
    (r"^(thanks|thank you|ty|thx|cheers)\b",                 THANKS),
    (r"^(hello|hi|hey|hiya|sup|yo)\b",                       HELLO),
    (r"^(how are you|how'?s it going|you okay)\b",           HOW_ARE_YOU),
    # "tell me about yourself" / "who are you" → short answer, no RAG
    (r"(tell me about yourself|who are you|what are you|describe yourself)", ABOUT_ME),
]


def get_shortcut_response(text: str) -> Optional[str]:
    """
    Returns a short natural response if text matches a shortcut.
    Returns None if no match — let the full pipeline handle it.
    """
    text_clean = text.lower().strip().rstrip("!.,?")
    for pattern, bank in RULES:
        if re.search(pattern, text_clean):
            return random.choice(bank)
    return None