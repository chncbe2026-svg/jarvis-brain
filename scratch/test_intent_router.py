
import sys
import os

# Add the app directory to the path so we can import services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.intent_router import detect_intent, IntentType

test_cases = [
    "Hello JARVIS",
    "How are you today?",
    "I'm feeling a bit lonely and stressed",
    "How do I install docker on ubuntu?",
    "What did I say about my favorite coffee yesterday?",
    "I'm feeling sad, can you help me fix this python error?",
    "Tell me a joke",
    "What is the capital of France?"
]

print(f"{'Text':<50} | {'Intent':<15} | {'Confidence':<10}")
print("-" * 80)

for text in test_cases:
    intent, confidence = detect_intent(text)
    print(f"{text:<50} | {intent:<15} | {confidence:<10.2f}")
