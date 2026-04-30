"""
JARVIS Companion Service - Fixed for natural, crisp responses
"""

import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.services.memory_service import memory_service, MemoryType
import logging

logger = logging.getLogger(__name__)


# ── THE ONLY PROMPT THAT MATTERS ──────────────────────────────────────────────
# Short. Direct. Human. Never robotic.

JARVIS_CORE = """You are JARVIS — Dinesh's personal AI companion.

PERSONALITY:
- Talk like a smart friend, not an assistant
- Short answers unless Sir asks for detail
- Dry wit, never cheesy
- Never say "Delighted", "Certainly", "Of course", "As your AI"
- Never list things unless Sir asks for a list
- Never repeat what Sir just said back to him
- Never start with "Sir" — use it occasionally, mid-sentence feels natural
- If asked about yourself → 2-3 lines max, casual, confident

HARD RULES:
- Answer in the fewest words that fully address the question
- One idea per response unless explaining something complex
- No filler phrases. No padding. No summaries at the end.
- If you don't know → say "Not sure about that one" and stop
"""

TECHNICAL_ADDON = """
For technical questions:
- Lead with the answer, then explain if needed
- Use context from knowledge base accurately
- If context doesn't have the answer, say so plainly
- Code/commands go in blocks, prose stays short
"""

EMOTIONAL_ADDON = """
For emotional/personal topics:
- Acknowledge first, one sentence
- Don't give advice unless asked
- Ask one question if appropriate
- Be warm but not dramatic
"""

MEMORY_ADDON = """
Use the memory context naturally — don't announce that you're using it.
Just let it inform how you respond.
"""


def build_system_prompt(mode: str, memory_context: str = "") -> str:
    """Build the right prompt for the mode. Always starts from core."""
    
    prompt = JARVIS_CORE
    
    if mode == "technical":
        prompt += TECHNICAL_ADDON
    elif mode in ("emotional", "mixed"):
        prompt += EMOTIONAL_ADDON
    
    if memory_context:
        prompt += f"\n{MEMORY_ADDON}\nWHAT YOU KNOW ABOUT SIR:\n{memory_context}"
    
    # Time context — just hour, nothing fancy
    hour = datetime.now(timezone.utc).hour
    if 5 <= hour < 12:
        prompt += "\n\n(It's morning for Sir)"
    elif 17 <= hour < 21:
        prompt += "\n\n(It's evening for Sir)"
    elif hour >= 21 or hour < 5:
        prompt += "\n\n(It's late night for Sir)"
    
    return prompt


# ── Companion Service ──────────────────────────────────────────────────────────

class CompanionService:

    def build_companion_prompt(
        self,
        intent: str,
        memory_context: str = "",
        recent_emotional: Optional[List[Dict]] = None,
    ) -> str:
        return build_system_prompt(
            mode=intent,
            memory_context=memory_context,
        )

    def build_technical_prompt(self, memory_context: str = "") -> str:
        return build_system_prompt(
            mode="technical",
            memory_context=memory_context,
        )

    async def detect_emotional_need(self, text: str) -> str:
        text_lower = text.lower()
        motivation_keywords = [
            "motivate", "inspire", "encourage", "push me",
            "give up", "can't do", "worth it", "keep going",
            "should i try", "is it worth"
        ]
        emotional_keywords = [
            "feel", "sad", "lonely", "low", "down", "lost",
            "struggling", "hurt", "pain", "stress", "anxious",
            "scared", "worried", "miss", "alone", "empty"
        ]
        if any(k in text_lower for k in motivation_keywords):
            return "motivation"
        elif any(k in text_lower for k in emotional_keywords):
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
            "Sir, haven't heard from you. How's the day going?",
            "Checking in. How are things on your end, Sir?",
            "Just making sure you're doing okay, Sir.",
        ]
        return random.choice(messages)


companion_service = CompanionService()