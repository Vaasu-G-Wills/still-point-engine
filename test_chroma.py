import sys
import os

# Add path so we can import from the engine
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import init_databases
import config

collection = init_databases()

if __name__ == "__main__":
    print(f"Current Configured Threshold: {config.SIMILARITY_THRESHOLD}")
    print("="*60)
    
    test_topics = [
        "The Commodification of Education",            # Exact Match
        "The Financialization of Higher Education",    # Conceptually identical
        "The Commodification of Healthcare",           # Similar structure, different domain
        "The Ethics of Artificial Intelligence",       # Completely different
    ]
    
    for test in test_topics:
        res = collection.query(query_texts=[test], n_results=1)
        sim = 0
        if res and "distances" in res and res["distances"]:
            distances = res["distances"][0]
            if distances:
                sim = 1.0 - distances[0]
        
        status = "❌ BLOCKED" if sim >= config.SIMILARITY_THRESHOLD else "✅ ALLOWED"
        print(f"  {sim:.4f} | {status} | {test}")
