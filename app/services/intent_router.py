"""
JARVIS Intent Router
Classifies user input into: CASUAL, TECHNICAL, EMOTIONAL, MIXED, GREETING
Routes to appropriate pipeline without wasting API calls.
"""

import re
from typing import Tuple
from enum import Enum


class IntentType(str, Enum):
    GREETING    = "greeting"      # hello, good morning, good night
    CASUAL      = "casual"        # how are you, what's up
    EMOTIONAL   = "emotional"     # I feel low, I'm stressed, lonely
    TECHNICAL   = "technical"     # RAG-worthy factual questions
    MEMORY      = "memory"        # how was my day, what did I say
    MIXED       = "mixed"         # emotional + technical blend
    PROACTIVE   = "proactive"     # check-ins, reminders (internal use)


# ── Pattern Banks ──────────────────────────────────────────────────────────────

GREETING_PATTERNS = [
    r"^(hello|hi|hey|hiya|howdy|sup|yo)\b",
    r"^good\s?(morning|afternoon|evening|night|day)\b",
    r"^(good\s?night|gn|g\.n\.)\b",
    r"^(thanks|thank you|ty|thx|cheers)\b",
    r"^(bye|goodbye|see you|cya|later|take care)\b",
    r"^(wake up|jarvis|hey jarvis)\b",
]

EMOTIONAL_PATTERNS = [
    r"\b(feel(ing)?|felt)\s+(low|sad|down|bad|lonely|lost|empty|tired|depressed|anxious|stressed|overwhelmed|hopeless|worthless)\b",
    r"\b(i('m| am))\s+(not okay|broken|struggling|falling apart|exhausted|burnt out|anxious|worried|scared|hopeless)\b",
    r"\b(nobody|no one)\s+(cares|understands|is there)\b",
    r"\b(miss|missing|alone|loneliness|isolation)\b",
    r"\b(can'?t\s+(sleep|focus|think|go on))\b",
    r"\b(need\s+(someone|support|help|motivation|a friend))\b",
    r"\b(life\s+is\s+(hard|tough|meaningless|difficult))\b",
    r"\bwhy\s+(bother|try|even)\b",
    r"\b(motivate|inspire|encourage)\s+me\b",
    r"\b(how\s+was\s+my\s+day|cheer\s+me\s+up|talk\s+to\s+me)\b",
]

MEMORY_PATTERNS = [
    r"\b(remember|recall|forgot|remind me)\b",
    r"\b(what did (i|we) (say|talk|discuss|do))\b",
    r"\bhow was (my|our) (day|week|morning|yesterday)\b",
    r"\bwhat('?s| is) my (goal|preference|plan|schedule)\b",
    r"\b(last time|previously|before|earlier)\b",
    r"\bdo you know (me|my|about)\b",
]

TECHNICAL_PATTERNS = [
    r"\b(how to|how do|what is|what are|explain|define|show me|give me|find|search|lookup)\b",
    r"\b(error|bug|issue|problem|fix|debug|troubleshoot)\b",
    r"\b(install|configure|setup|deploy|run|build|compile)\b",
    r"\b(api|server|database|query|endpoint|docker|kubernetes)\b",
    r"\b(price|cost|compare|vendor|product|spec|feature)\b",
    r"\b(code|script|function|class|module|library)\b",
    r"\b(network|ip|dns|firewall|vpn|ssh|port)\b",
    r"\?$",  # ends with question mark (likely factual)
]

CASUAL_PATTERNS = [
    r"^(what'?s up|wassup|how are you|how'?s it going|how do you do)\b",
    r"\b(bored|nothing to do|just chatting|random(ly)?)\b",
    r"\b(tell me (something|a joke|a story|anything))\b",
    r"\b(what do you think|your opinion|do you like)\b",
    r"\b(fun fact|interesting|cool|awesome|wow)\b",
]


def _matches(text: str, patterns: list) -> bool:
    """Check if text matches any pattern in the list."""
    text_lower = text.lower().strip()
    return any(re.search(p, text_lower) for p in patterns)


def _score_intent(text: str) -> dict:
    """Return confidence scores for each intent type."""
    return {
        IntentType.GREETING:   2.0 if _matches(text, GREETING_PATTERNS) else 0.0,
        IntentType.EMOTIONAL:  1.8 if _matches(text, EMOTIONAL_PATTERNS) else 0.0,
        IntentType.MEMORY:     1.6 if _matches(text, MEMORY_PATTERNS)   else 0.0,
        IntentType.TECHNICAL:  1.4 if _matches(text, TECHNICAL_PATTERNS) else 0.0,
        IntentType.CASUAL:     1.0 if _matches(text, CASUAL_PATTERNS)   else 0.0,
    }


def detect_intent(text: str) -> Tuple[IntentType, float]:
    """
    Returns (IntentType, confidence_score).
    Handles MIXED when both emotional + technical score high.
    """
    scores = _score_intent(text)
    
    # Check for MIXED: both emotional and technical triggered
    emotional_score  = scores[IntentType.EMOTIONAL]
    technical_score  = scores[IntentType.TECHNICAL]
    
    if emotional_score > 0 and technical_score > 0:
        return IntentType.MIXED, (emotional_score + technical_score) / 2

    # Pick highest scoring intent
    best_intent = max(scores, key=scores.get)
    best_score  = scores[best_intent]

    # Default to TECHNICAL if nothing matched (assume it needs RAG)
    if best_score == 0.0:
        return IntentType.TECHNICAL, 0.5

    return best_intent, best_score


def should_use_rag(intent: IntentType) -> bool:
    """Determines if RAG retrieval should be triggered."""
    return intent in {IntentType.TECHNICAL, IntentType.MIXED, IntentType.MEMORY}


def should_use_companion(intent: IntentType) -> bool:
    """Determines if companion/emotional mode should be used."""
    return intent in {
        IntentType.GREETING,
        IntentType.CASUAL,
        IntentType.EMOTIONAL,
        IntentType.MIXED,
    }
