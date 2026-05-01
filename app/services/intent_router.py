"""
JARVIS Intent Router — Complete Brain
Understands what Sir means, not just what he says.
"""

import re
from typing import Tuple, Optional
from enum import Enum

from app.services.companion_service import matches_human_pattern


class IntentType(str, Enum):
    GREETING  = "greeting"
    CASUAL    = "casual"
    EMOTIONAL = "emotional"
    TECHNICAL = "technical"
    MEMORY    = "memory"
    MIXED     = "mixed"


# ── Pattern definitions ────────────────────────────────────────────────────────

GREETING_PATTERNS = [
    r"^(hello|hi|hey|hiya|howdy|sup|yo)\b",
    r"^good\s?(morning|afternoon|evening|night|day)\b",
    r"^(gn|g\.n\.)\b",
    r"^(thanks|thank you|ty|thx|cheers|appreciated)\b",
    r"^(bye|goodbye|see you|later|take care|cya)\b",
    r"^(wake up|jarvis|hey jarvis|you there|you online)\b",
    r"^(tell me about yourself|who are you|what are you)\b",
]

EMOTIONAL_PATTERNS = [
    r"\b(feel(ing)?|felt)\b",
    r"\bi'?m\s+(good|great|fine|bad|low|sad|tired|happy|excited|"
    r"bored|stressed|anxious|lonely|lost|overwhelmed|motivated|"
    r"productive|focused|sluggish|off|down|not okay|not great|"
    r"struggling|burnt out|exhausted|frustrated|scared|worried|"
    r"empty|numb|broken|stuck|confused|hopeless|helpless)\b",
    r"\b(not okay|falling apart|can'?t focus|can'?t sleep|"
    r"can'?t think|need a break|losing it|breaking down)\b",
    r"\b(miss|alone|lonely|empty|hurt|numb)\b",
    r"\b(nobody|no one)\s+(cares|understands|is there|gets it)\b",
    r"\b(today was|today is|had a)\s+(good|bad|long|rough|great|"
    r"terrible|amazing|awful|weird|hard|tough|easy)\b",
    r"\b(been a)\s+(good|bad|long|rough|great|hard|tough|weird)\s+\b",
    r"\b(nothing is|everything is)\s+(working|fine|okay|broken|falling apart)\b",
]

MEMORY_PATTERNS = [
    r"\b(remember|recall|remind me|forgot|do you know|who is|tell me about)\b",
    r"\bwhat did (i|we) (say|talk|discuss|do|work on)\b",
    r"\bhow was (my|our) (day|week|morning|yesterday|last session)\b",
    r"\bwhat'?s? (my|our) (goal|preference|plan|schedule|target)\b",
    r"\b(last time|previously|earlier today|before|last week)\b",
    r"\bdo you (know|remember) (me|my|about|what)\b",
]

CASUAL_PATTERNS = [
    r"^(what'?s up|wassup|how are you|how'?s it going|you okay)\b",
    r"\b(bored|nothing to do|just chatting|just talking|just venting)\b",
    r"\b(tell me (a joke|a story|something|anything))\b",
    r"\b(what do you think|your opinion|do you like|do you prefer)\b",
    r"\b(worked on|been thinking|been working|spent time on)\b",
    r"\b(productive|unproductive|lazy|on a roll|in the zone)\b",
    r"\b(just wanted to|needed to|had to)\s+(say|tell|share|vent)\b",
    r"\b(checking in|just checking)\b",
]

TECHNICAL_PATTERNS = [
    r"\b(how to|how do i|how does|how can i)\b",
    r"\b(what is|who is|what are|what does|explain|define|tell me about)\b",
    r"\b(show me|give me|find|search|look up|lookup)\b",
    r"\b(error|bug|issue|fix|debug|troubleshoot|broken|crash|not starting)\b",
    r"\b(install|configure|setup|deploy|run|build|compile|start|stop|restart)\b",
    r"\b(api|server|database|query|endpoint|docker|kubernetes|k8s|container)\b",
    r"\b(price|cost|compare|vendor|product|spec|feature|review|difference)\b",
    r"\b(code|script|function|class|module|library|framework|package)\b",
    r"\b(network|ip address|dns|firewall|vpn|ssh|port|protocol|subnet)\b",
    r"\b(command|terminal|shell|bash|linux|windows|python|javascript|sql)\b",
    r"\b(log|logs|monitoring|metrics|alert|warning|critical|severity)\b",
]


def _match(text: str, patterns: list) -> bool:
    t = text.lower().strip()
    return any(re.search(p, t) for p in patterns)


def detect_intent(text: str) -> Tuple[IntentType, float]:
    """
    Understand what Sir actually means.

    Priority order (highest to lowest):
    1. Greeting       — fastest exit, no LLM needed
    2. Human Pattern  — safety net against false technical routing
    3. Emotional      — feelings always beat technical patterns
    4. Memory         — questions about the past
    5. Casual         — general chat, mood updates
    6. Technical      — only if clearly a specific question/task
    7. Smart fallback — short message without ? = casual
    """
    text_strip = text.strip()

    # ── 1. Greeting ───────────────────────────────────────────────────────────
    if _match(text_strip, GREETING_PATTERNS):
        return IntentType.GREETING, 1.0

    # ── 2. Human Pattern Safety Net ───────────────────────────────────────────
    # Catches things like "is everything working fine" before
    # they accidentally match technical patterns
    human_pattern = matches_human_pattern(text_strip)
    if human_pattern in (
        "checking_in",
        "mood_updates",
        "connection",
        "false_technical",
    ):
        return IntentType.CASUAL, 0.95

    if human_pattern == "soft_help":
        # Could be emotional or casual — check for distress
        if _match(text_strip, EMOTIONAL_PATTERNS):
            return IntentType.EMOTIONAL, 0.9
        return IntentType.CASUAL, 0.85

    # ── 3. Emotional ──────────────────────────────────────────────────────────
    # Feelings always beat technical patterns
    # "I'm stressed and my server crashed" → MIXED, not pure technical
    is_emotional = _match(text_strip, EMOTIONAL_PATTERNS)
    is_technical = _match(text_strip, TECHNICAL_PATTERNS)

    if is_emotional and is_technical:
        return IntentType.MIXED, 0.9

    if is_emotional:
        return IntentType.EMOTIONAL, 0.95

    # ── 4. Memory ─────────────────────────────────────────────────────────────
    if _match(text_strip, MEMORY_PATTERNS):
        return IntentType.MEMORY, 0.9

    # ── 5. Casual ─────────────────────────────────────────────────────────────
    if _match(text_strip, CASUAL_PATTERNS):
        return IntentType.CASUAL, 0.85

    # ── 6. Technical ──────────────────────────────────────────────────────────
    if is_technical:
        return IntentType.TECHNICAL, 0.85

    # ── 7. Smart Fallback ─────────────────────────────────────────────────────
    words = text_strip.split()

    # Short message without question mark = casual
    if len(words) <= 8 and "?" not in text_strip:
        return IntentType.CASUAL, 0.7

    # Ends with ? = probably wants an answer = technical
    if text_strip.endswith("?"):
        return IntentType.TECHNICAL, 0.6

    # Long message, no clear signal = casual (Sir is talking, not querying)
    return IntentType.CASUAL, 0.55


def should_use_rag(intent: IntentType) -> bool:
    return intent in {
        IntentType.TECHNICAL,
        IntentType.MIXED,
        IntentType.MEMORY,
    }


def should_use_companion(intent: IntentType) -> bool:
    return intent in {
        IntentType.GREETING,
        IntentType.CASUAL,
        IntentType.EMOTIONAL,
        IntentType.MIXED,
    }