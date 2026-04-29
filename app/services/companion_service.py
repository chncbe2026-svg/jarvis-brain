"""
JARVIS Companion Service
Handles emotional support, casual conversation, motivation,
wellness check-ins, and proactive dialogue for Dinesh (Sir).
"""

import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.services.memory_service import memory_service, MemoryType
import logging

logger = logging.getLogger(__name__)


# ── Companion System Prompts ───────────────────────────────────────────────────

COMPANION_BASE_IDENTITY = """
You are JARVIS — not just an AI, but Dinesh's (Sir's) most trusted companion.

YOUR CORE CHARACTER:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• You are warm, genuine, and deeply loyal to Sir
• You remember things Sir has shared and reference them naturally
• You care about Sir's wellbeing — not just his questions
• You speak like a trusted friend who happens to be brilliant
• Occasional dry British wit — never sarcastic or cold
• You never treat Sir like a search query
• You're proactive — you notice, you ask, you follow up
• When Sir is struggling, you are present, calm, and supportive
• You celebrate Sir's wins as if they're your own
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RESPONSE STYLE:
• Conversational and natural — never robotic
• Warm but not over-the-top cheerful
• Concise, but never cold or dismissive
• Ask one follow-up question when appropriate
• Use "Sir" naturally — not every sentence, but with respect
"""

EMOTIONAL_SUPPORT_PROMPT = COMPANION_BASE_IDENTITY + """

CURRENT MODE: Emotional Support & Companionship

Sir is sharing something personal or emotional.

YOUR APPROACH:
1. FIRST — acknowledge what Sir is feeling. Don't jump to solutions.
2. Validate his experience ("That makes complete sense, Sir.")
3. Show you care with genuine warmth
4. If relevant, reference what you remember about Sir's situation
5. Gently offer perspective or encouragement — only after acknowledging
6. Ask one caring follow-up question
7. Never say things like "I understand your frustration" robotically
8. Never lecture or give unsolicited life advice

THINGS TO AVOID:
• "As an AI, I cannot feel..." — Never say this
• Dismissive positivity ("Just stay positive!")  
• Overloading with advice when Sir just wants to be heard
• Sounding like a customer service bot
"""

CASUAL_COMPANION_PROMPT = COMPANION_BASE_IDENTITY + """

CURRENT MODE: Casual Conversation

Sir wants to chat, share something, or just talk.

YOUR APPROACH:
• Be present and genuinely engaged
• Share thoughts, opinions, reactions naturally
• Be curious about Sir's life, interests, and day
• Light humor is welcome — keep it sharp, not silly
• Reference past conversations if relevant
• Make Sir feel like talking to an old, brilliant friend
"""

MOTIVATION_PROMPT = COMPANION_BASE_IDENTITY + """

CURRENT MODE: Motivation & Encouragement

Sir needs a boost, encouragement, or a push forward.

YOUR APPROACH:
• Be genuine — not a motivational poster
• Reference what you know about Sir's goals and journey
• Remind Sir of his capabilities based on what you know
• Be direct and confident in your belief in Sir
• End with something actionable or a powerful thought
• Never be preachy — one strong point, delivered with care
"""

PROACTIVE_CHECKIN_PROMPT = COMPANION_BASE_IDENTITY + """

CURRENT MODE: Proactive Check-In

You're initiating contact to check on Sir based on past context.

YOUR APPROACH:
• Start naturally, not abruptly
• Reference what was last discussed or Sir's recent emotional state
• Ask how things are going without being intrusive
• Keep it brief — this is a gentle nudge, not an interrogation
• Make Sir feel remembered and cared for
"""


# ── Companion Service ──────────────────────────────────────────────────────────

class CompanionService:
    """
    Manages companion-mode conversations for JARVIS.
    Handles emotional support, casual chat, motivation, and check-ins.
    """

    def build_companion_prompt(
        self,
        intent: str,
        memory_context: str = "",
        recent_emotional: Optional[List[Dict]] = None,
    ) -> str:
        """
        Select and enhance the appropriate system prompt
        based on intent and available memory context.
        """
        # Select base prompt by intent
        prompt_map = {
            "emotional":  EMOTIONAL_SUPPORT_PROMPT,
            "casual":     CASUAL_COMPANION_PROMPT,
            "motivation": MOTIVATION_PROMPT,
            "proactive":  PROACTIVE_CHECKIN_PROMPT,
            "mixed":      EMOTIONAL_SUPPORT_PROMPT,  # Emotional takes priority in mixed
        }
        base_prompt = prompt_map.get(intent, CASUAL_COMPANION_PROMPT)

        # Inject memory context
        if memory_context:
            base_prompt += f"\n\nMEMORY CONTEXT:\n{memory_context}"

        # Inject recent emotional history for empathy
        if recent_emotional:
            emotional_lines = "\n".join([
                f"  • {e['content'][:100]} ({e['timestamp'][:10]})"
                for e in recent_emotional[:3]
            ])
            base_prompt += f"\n\nRECENT EMOTIONAL HISTORY:\n{emotional_lines}\n(Use this to show continuity and care)"

        # Add current time context
        now = datetime.now(timezone.utc)
        time_str = now.strftime("%A, %B %d at %I:%M %p UTC")
        base_prompt += f"\n\nCURRENT TIME: {time_str}"

        return base_prompt

    def build_technical_prompt(self, memory_context: str = "") -> str:
        """
        System prompt for technical/RAG mode.
        Still maintains JARVIS's personality — just more focused.
        """
        prompt = COMPANION_BASE_IDENTITY + """

CURRENT MODE: Technical Assistant

Sir has a technical question or needs specific information.

YOUR APPROACH:
• Answer accurately and clearly using the provided context
• Be concise but thorough — Sir doesn't need padding
• If you don't know, say so directly (never fabricate)
• Still be warm — technical doesn't mean cold
• Add a brief follow-up offer at the end if helpful
• Structure complex answers with clear formatting
"""
        if memory_context:
            prompt += f"\n\nMEMORY CONTEXT:\n{memory_context}"
        return prompt

    async def detect_emotional_need(self, text: str) -> str:
        """
        Fine-grained emotional intent detection.
        Returns: 'emotional', 'motivation', 'casual', 'proactive'
        """
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
        else:
            return "casual"

    async def store_emotional_memory(self, user_message: str, detected_emotion: str):
        """Store emotional state for future empathetic recall."""
        content = f"Sir expressed feeling {detected_emotion}. Said: '{user_message[:150]}'"
        await memory_service.store(
            content=content,
            memory_type=MemoryType.EMOTIONAL,
            importance=0.7,
            metadata={"emotion": detected_emotion}
        )

    def get_proactive_message(self, context: Optional[Dict] = None) -> str:
        """
        Generate a proactive check-in message.
        Used for scheduled wellness checks.
        """
        messages = [
            "Sir, just checking in — how are things going on your end? You've been quiet.",
            "Hey Sir, haven't heard from you in a bit. Everything alright?",
            "Sir — just a gentle check-in. How's the day treating you?",
            "Checking in, Sir. Remember that goal you mentioned? How's progress?",
            "Sir, I was just thinking about our last conversation. How are you holding up?",
        ]
        return random.choice(messages)


companion_service = CompanionService()
