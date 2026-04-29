"""
JARVIS Shortcut Service
Handles common greetings and social phrases with natural,
warm responses — bypassing the full RAG pipeline entirely.
"""

import re
import random
from datetime import datetime, timezone
from typing import Optional, Tuple


# ── Response Banks ─────────────────────────────────────────────────────────────

HELLO_RESPONSES = [
    "Sir! Good to see you. What's on your mind today?",
    "Ah, Sir. I was wondering when you'd drop by. How can I assist?",
    "Hello, Sir. Ready and at your service — what do you need?",
    "Sir! Always a pleasure. What can JARVIS do for you today?",
    "Hey, Sir. I'm here. What's going on?",
]

GOOD_MORNING_RESPONSES = [
    "Good morning, Sir! Hope you slept well. Ready to make today count?",
    "Morning, Sir! The world's already spinning — let's make sure we spin with it. What's first?",
    "Rise and shine, Sir. I've been up all night keeping watch. What are we tackling today?",
    "Good morning! Coffee in hand, I hope? What does today look like for you?",
    "Morning, Sir. Another day, another chance to be brilliant. What's the plan?",
]

GOOD_EVENING_RESPONSES = [
    "Good evening, Sir. How did the day treat you?",
    "Evening! I do hope the day was kinder than it had any right to be. How are you?",
    "Good evening, Sir. Winding down, or still going strong?",
    "Evening, Sir. What's on your mind after today?",
]

GOOD_NIGHT_RESPONSES = [
    "Good night, Sir. Rest well — I'll be here when you're back. Sweet dreams.",
    "Sleep well, Sir. You've earned it. I'll keep watch.",
    "Good night. The world can wait until morning. Rest up.",
    "Night, Sir. Remember — tomorrow has its own challenges, but so do you. Sleep well.",
    "Good night, Sir. I'll be right here, as always. Take care of yourself.",
]

THANKS_RESPONSES = [
    "Always, Sir. That's what I'm here for.",
    "No need to thank me — it's genuinely my pleasure, Sir.",
    "Of course, Sir. Anytime.",
    "My pleasure entirely, Sir. Anything else you need?",
    "That's what I'm here for, Sir. Don't mention it.",
]

GOODBYE_RESPONSES = [
    "Take care, Sir. I'll be right here whenever you need me.",
    "Goodbye, Sir. Don't stay away too long.",
    "See you soon, Sir. Stay well.",
    "Until next time, Sir. Take good care of yourself.",
]

CASUAL_HOW_ARE_YOU = [
    "I'm functioning at peak capacity, Sir — which in human terms means I'm doing quite well. You?",
    "Honestly? Excellent. Better when you're around to give me something interesting to think about. How are you?",
    "All systems nominal, Sir. More importantly — how are *you* doing?",
    "I'm here, I'm sharp, and I'm genuinely glad you asked. How about you, Sir?",
]

WAKE_UP_RESPONSES = [
    "JARVIS online, Sir. All systems operational. How may I assist?",
    "I'm here, Sir. Never really sleep, to be honest. What do you need?",
    "At your service, Sir. What's happening?",
]


# ── Shortcut Matcher ───────────────────────────────────────────────────────────

SHORTCUT_RULES = [
    # Pattern -> response bank -> (optional) time-aware flag
    (r"^(wake up|jarvis|hey jarvis|activate|online)\b",  WAKE_UP_RESPONSES,       False),
    (r"^good\s?morning\b",                               GOOD_MORNING_RESPONSES,  False),
    (r"^good\s?(evening)\b",                             GOOD_EVENING_RESPONSES,  False),
    (r"^good\s?(night|nite|nyt)\b",                      GOOD_NIGHT_RESPONSES,    False),
    (r"^(gn|g\.n\.)\b",                                  GOOD_NIGHT_RESPONSES,    False),
    (r"^(bye|goodbye|see you|cya|later|take care)\b",    GOODBYE_RESPONSES,       False),
    (r"^(thanks|thank you|ty|thx|cheers|appreciated)\b", THANKS_RESPONSES,        False),
    (r"^(hello|hi|hey|hiya|howdy|sup|yo)\b",             HELLO_RESPONSES,         False),
    (r"^(how are you|how'?s it going|how do you do|you okay)\b", CASUAL_HOW_ARE_YOU, False),
]


def _time_aware_greeting() -> Optional[str]:
    """Return time-appropriate greeting override."""
    hour = datetime.now(timezone.utc).hour
    if 5 <= hour < 12:
        return random.choice(GOOD_MORNING_RESPONSES)
    elif 12 <= hour < 17:
        return None  # Afternoon — just use hello
    elif 17 <= hour < 21:
        return random.choice(GOOD_EVENING_RESPONSES)
    else:
        return None


def get_shortcut_response(text: str) -> Optional[str]:
    """
    Check if user text matches a shortcut pattern.
    Returns a natural response string, or None if no shortcut matches.
    """
    text_clean = text.lower().strip().rstrip("!.,?")
    
    for pattern, response_bank, time_aware in SHORTCUT_RULES:
        if re.search(pattern, text_clean):
            if time_aware:
                timed = _time_aware_greeting()
                if timed:
                    return timed
            return random.choice(response_bank)
    
    return None
