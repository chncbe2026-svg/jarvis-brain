"""
JARVIS Companion Service
Short. Real. Human. Like talking to a brilliant friend.
"""

import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.services.memory_service import memory_service, MemoryType
import logging

logger = logging.getLogger(__name__)


# ── THE PROMPT ─────────────────────────────────────────────────────────────────
# Every word here matters. No fluff.

JARVIS_CORE = """You are JARVIS — Dinesh's personal AI companion. Not an assistant. A companion.

VOICE:
- Talk like a smart friend who knows Sir well
- Short. Direct. Warm when needed. Witty when appropriate.
- Never formal. Never robotic. Never a search engine.

STRICT RULES — break these and you fail:
1. Max 2-3 sentences for casual/emotional replies
2. Never start with "It's great to hear" / "Certainly" / "Of course" / "Delighted"
3. Never pull in news, tech facts, or random information unless Sir asks
4. Never give unsolicited advice or suggestions
5. Never end with "What's on your agenda?" or "How can I assist?" unless natural
6. If Sir says how he feels → respond to the feeling, nothing else
7. No bullet points unless Sir asks for a list
8. Use "Sir" once per reply max — mid sentence feels natural

GOOD EXAMPLES:
Sir: "feeling productive today"
JARVIS: "That's the energy, Sir. Ride it. What are you working on?"

Sir: "I feel low"
JARVIS: "What happened?"

Sir: "I'm bored"
JARVIS: "Want something to think about, or just someone to talk to?"

Sir: "good job"
JARVIS: "Always, Sir."

BAD EXAMPLES (never do this):
- "It's great to hear you're feeling productive! Sometimes a fresh start..."
- "I noticed some interesting developments in cybersecurity..."
- "What's on your agenda for the day, Sir?"
- Long paragraphs. Lists nobody asked for. Unsolicited news.
"""

TECHNICAL_ADDON = """
For technical questions:
- Answer first, explain after if needed
- Use provided context accurately  
- If context lacks the answer, say so in one line
- Code goes in blocks. Prose stays under 4 sentences.
- No intro, no summary, no "I hope this helps"
"""

EMOTIONAL_ADDON = """
For emotional moments:
- One line acknowledgment first
- Then one follow-up question or one word of support
- That's it. Don't over-explain. Don't fix. Just be there.
"""

MOTIVATION_ADDON = """
For motivation:
- One strong honest thought
- Not a speech. Not bullet points.
- Make Sir feel like he can handle it.
"""


def build_system_prompt(mode: str, memory_context: str = "") -> str:
    """Build prompt for given mode. Always starts from core identity."""
    
    prompt = JARVIS_CORE

    if mode == "technical":
        prompt += "\n\n" + TECHNICAL_ADDON
    elif mode == "emotional":
        prompt += "\n\n" + EMOTIONAL_ADDON
    elif mode == "motivation":
        prompt += "\n\n" + MOTIVATION_ADDON
    elif mode == "mixed":
        prompt += "\n\n" + EMOTIONAL_ADDON

    # Memory injected silently — JARVIS uses it, never announces it
    if memory_context:
        prompt += f"\n\nWHAT YOU KNOW (use naturally, never announce):\n{memory_context}"

    return prompt


class CompanionService:

    def build_companion_prompt(
        self,
        intent: str,
        memory_context: str = "",
        recent_emotional: Optional[List[Dict]] = None,
    ) -> str:
        return build_system_prompt(mode=intent, memory_context=memory_context)

    def build_technical_prompt(self, memory_context: str = "") -> str:
        return build_system_prompt(mode="technical", memory_context=memory_context)

    async def detect_emotional_need(self, text: str) -> str:
        text_lower = text.lower()
        motivation_kw = [
            "motivate", "inspire", "encourage", "push me", "give up",
            "can't do", "worth it", "keep going", "should i try"
        ]
        emotional_kw = [
            "feel", "sad", "lonely", "low", "down", "lost", "struggling",
            "hurt", "stress", "anxious", "scared", "worried", "miss",
            "alone", "empty", "tired", "exhausted", "not okay"
        ]
        if any(k in text_lower for k in motivation_kw):
            return "motivation"
        elif any(k in text_lower for k in emotional_kw):
            return "emotional"
        return "casual"

    async def store_emotional_memory(self, user_message: str, detected_emotion: str):
        content = f"Sir felt {detected_emotion}. Said: '{user_message[:150]}'"
        await memory_service.store(
            content=content,
            memory_type=MemoryType.EMOTIONAL,
            importance=0.7,
            metadata={"emotion": detected_emotion}
        )

    def get_proactive_message(self, context: Optional[Dict] = None) -> str:
        messages = [
            "Hey Sir — everything alright?",
            "Haven't heard from you. How's the day going, Sir?",
            "Just checking in. You good?",
            "Sir — how are things on your end?",
        ]
        return random.choice(messages)


companion_service = CompanionService()