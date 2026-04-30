"""
JARVIS Intent Router
Classifies what Sir actually means — not just what words he uses.
"""

import re
from typing import Tuple
from enum import Enum


class IntentType(str, Enum):
    GREETING   = "greeting"
    CASUAL     = "casual"
    EMOTIONAL  = "emotional"
    TECHNICAL  = "technical"
    MEMORY     = "memory"
    MIXED      = "mixed"
    PROACTIVE  = "proactive"


# ── Emotional / Feeling patterns — checked FIRST, highest priority ─────────────
# "feeling productive", "feeling good", "feeling low" — ALL are emotional/casual
# They must never route to RAG

EMOTIONAL_PATTERNS = [
    # "feeling X" — any feeling word including positive ones
    r"\b(feel(ing)?|felt)\b",

    # "I am X" emotional states
    r"\bi'?m\s+(good|great|fine|okay|ok|bad|low|sad|tired|happy|excited|bored|"
    r"stressed|anxious|lonely|lost|overwhelmed|motivated|productive|focused|"
    r"sluggish|off|down|not okay|not great|struggling|burnt out|exhausted)\b",

    # direct emotional phrases
    r"\b(not okay|falling apart|can'?t focus|can'?t sleep|need a break)\b",
    r"\b(miss|alone|lonely|empty|hurt|pain|numb)\b",
    r"\b(nobody|no one)\s+(cares|understands|is there)\b",
]

GREETING_PATTERNS = [
    r"^(hello|hi|hey|hiya|howdy|sup|yo)\b",
    r"^good\s?(morning|afternoon|evening|night|day)\b",
    r"^(gn|g\.n\.)\b",
    r"^(thanks|thank you|ty|thx|cheers|appreciated)\b",
    r"^(bye|goodbye|see you|cya|later|take care)\b",
    r"^(wake up|jarvis|hey jarvis)\b",
    r"^(tell me about yourself|who are you|what are you)\b",
]

MEMORY_PATTERNS = [
    r"\b(remember|recall|remind me|forgot)\b",
    r"\bwhat did (i|we) (say|talk|discuss|do)\b",
    r"\bhow was (my|our) (day|week|morning|yesterday)\b",
    r"\bwhat'?s? (my|our) (goal|preference|plan|schedule)\b",
    r"\b(last time|previously|earlier today|before)\b",
    r"\bdo you (know|remember) (me|my|about)\b",
]

CASUAL_PATTERNS = [
    r"^(what'?s up|wassup|how are you|how'?s it going)\b",
    r"\b(bored|nothing to do|just chatting)\b",
    r"\b(tell me (a joke|a story|something interesting|anything))\b",
    r"\b(what do you think|your opinion|do you like)\b",
    r"\b(today was|today is|had a (good|bad|long|weird|great|rough) day)\b",
    r"\b(worked on|spent time|been thinking|been working)\b",
    # Productivity/mood updates that are NOT questions
    r"\b(productive|unproductive|lazy|on a roll|in the zone|killing it|struggling today)\b",
]

# Technical — checked LAST, only if nothing else matches
TECHNICAL_PATTERNS = [
    r"\b(how to|how do i|how does|how can i)\b",
    r"\b(what is|what are|what does|explain|define)\b",
    r"\b(show me|give me|find|search|look up|lookup)\b",
    r"\b(error|bug|issue|fix|debug|troubleshoot|broken)\b",
    r"\b(install|configure|setup|deploy|run|build|compile)\b",
    r"\b(api|server|database|query|endpoint|docker|kubernetes|k8s)\b",
    r"\b(price|cost|compare|vendor|product|spec|feature|review)\b",
    r"\b(code|script|function|class|module|library|framework)\b",
    r"\b(network|ip address|dns|firewall|vpn|ssh|port|protocol)\b",
    r"\b(command|terminal|shell|bash|linux|windows|python|javascript)\b",
]


def _matches(text: str, patterns: list) -> bool:
    text_lower = text.lower().strip()
    return any(re.search(p, text_lower) for p in patterns)


def detect_intent(text: str) -> Tuple[IntentType, float]:
    """
    Classify Sir's intent.
    
    Order matters:
    1. Greeting  — fastest exit
    2. Emotional — must beat technical (feelings ≠ queries)
    3. Memory    — questions about the past
    4. Casual    — mood updates, general chat
    5. Technical — only if nothing above matched
    
    Mixed = emotional + technical both present
    """
    text_strip = text.strip()

    # ── 1. Greeting (short phrases at start of message) ───────────────────────
    if _matches(text_strip, GREETING_PATTERNS):
        return IntentType.GREETING, 1.0

    # ── 2. Emotional (feelings take priority over everything) ──────────────────
    is_emotional = _matches(text_strip, EMOTIONAL_PATTERNS)
    is_technical = _matches(text_strip, TECHNICAL_PATTERNS)

    if is_emotional and is_technical:
        # Mixed: "I feel stressed, how do I fix this error?"
        return IntentType.MIXED, 0.9

    if is_emotional:
        # Pure emotional: "feeling productive", "I'm low", "feeling good"
        return IntentType.EMOTIONAL, 0.95

    # ── 3. Memory ──────────────────────────────────────────────────────────────
    if _matches(text_strip, MEMORY_PATTERNS):
        return IntentType.MEMORY, 0.9

    # ── 4. Casual ─────────────────────────────────────────────────────────────
    if _matches(text_strip, CASUAL_PATTERNS):
        return IntentType.CASUAL, 0.85

    # ── 5. Technical (default for actual questions) ────────────────────────────
    if is_technical:
        return IntentType.TECHNICAL, 0.85

    # ── 6. Fallback — short messages without ? are usually casual ─────────────
    if len(text_strip.split()) <= 6 and "?" not in text_strip:
        return IntentType.CASUAL, 0.6

    # Longer messages without clear signal → technical (has enough words to be a query)
    return IntentType.TECHNICAL, 0.5


def should_use_rag(intent: IntentType) -> bool:
    return intent in {IntentType.TECHNICAL, IntentType.MIXED, IntentType.MEMORY}


def should_use_companion(intent: IntentType) -> bool:
    return intent in {
        IntentType.GREETING,
        IntentType.CASUAL,
        IntentType.EMOTIONAL,
        IntentType.MIXED,
    }