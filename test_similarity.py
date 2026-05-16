import sys
import os

# Add path so we can import from the engine
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_all_scripts
import ollama
import config

def dot_product(a, b):
    return sum(x * y for x, y in zip(a, b))

def magnitude(a):
    return sum(x * x for x in a) ** 0.5

def get_similarity(topic1, topic2):
    pad1 = f"search_document: {topic1}"
    pad2 = f"search_query: {topic2}"
    embed1 = ollama.embeddings(model=config.EMBED_MODEL, prompt=pad1)['embedding']
    embed2 = ollama.embeddings(model=config.EMBED_MODEL, prompt=pad2)['embedding']
    return dot_product(embed1, embed2) / (magnitude(embed1) * magnitude(embed2))

if __name__ == "__main__":
    past_scripts = get_all_scripts()
    if not past_scripts:
        print("No prior scripts found in DB to test against.")
        sys.exit(0)
        
    print(f"Current Configured Threshold: {config.SIMILARITY_THRESHOLD}")
    print("="*60)
    
    test_topics = [
        "The Commodification of Education",            # Exact Match
        "The Financialization of Higher Education",    # Conceptually identical
        "The Monetization of Public Schools",          # Conceptually identical
        "The Commodification of Healthcare",           # Similar structure, different domain
        "The Ethics of Artificial Intelligence",       # Completely different
        "Is College Worth the Cost?",                  # Same domain, different phrasing
    ]
    
    for past in past_scripts:
        past_topic = past['topic']
        print(f"\nPrior Saved Topic: '{past_topic}'")
        print("-" * 60)
        
        for test in test_topics:
            sim = get_similarity(past_topic, test)
            status = "❌ BLOCKED" if sim >= config.SIMILARITY_THRESHOLD else "✅ ALLOWED"
            print(f"  {sim:.4f} | {status} | {test}")
