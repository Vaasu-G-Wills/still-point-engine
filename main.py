import argparse
import sys
from pipeline import run_pipeline

def cli_callback(event, data):
    if event == "status":
        print(f"\n[SYSTEM] {data}")
    elif event == "exclusions":
        print("\n[!] Applying Reverse-RAG Exclusions:")
        for ex in data:
            # truncate for display
            display_text = ex[:100] + "..." if len(ex) > 100 else ex
            print(f"    - {display_text}")
    elif event in ["thesis", "antithesis", "synthesis"]:
        print(f"\n--- {event.upper()} ---\n")
        print(data)

def main():
    parser = argparse.ArgumentParser(description="The Still Point Script Engine CLI")
    parser.add_argument("topic", type=str, help="The core topic to generate a script about.")
    parser.add_argument("--debug", action="store_true", help="Cap outputs at 150 words per node for testing")
    args = parser.parse_args()

    import config
    config.DEBUG_MODE = args.debug

    try:
        print(f"Initializing Still Point Engine for topic: '{args.topic}' (DEBUG: {args.debug})")
        output = run_pipeline(args.topic, yield_callback=cli_callback)
        print(f"\n[+] Script saved successfully with {output['word_count']} words.")
    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
