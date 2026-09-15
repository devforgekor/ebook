import json
import logging
import argparse
from pathlib import Path
from semantic_cache import SemanticCache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

def pre_populate_cache(jsonl_path: Path):
    if not jsonl_path.exists():
        logger.error(f"File not found: {jsonl_path}")
        return

    cache = SemanticCache()
    
    count = 0
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
                messages = data.get("messages", [])
                
                # Extract last user-assistant pair
                user_content = ""
                assistant_content = ""
                
                # Simplistic extraction: find the last pair
                for msg in reversed(messages):
                    if msg["role"] == "assistant" and not assistant_content:
                        assistant_content = msg["content"]
                    elif msg["role"] == "user" and assistant_content and not user_content:
                        user_content = msg["content"]
                        break
                
                if user_content and assistant_content:
                    # Check if already exists (simplified: avoid adding same message)
                    # For pre-populating a large set, we might want to batch this.
                    cache.add(user_content, assistant_content, metadata=data.get("metadata"))
                    count += 1
                    if count % 100 == 0:
                        logger.info(f"Added {count} items to cache...")
            except Exception as e:
                logger.warning(f"Failed to process line: {e}")
                
    cache.save()
    logger.info(f"Pre-population complete. Total {count} items added.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("chat_backup/processed/chat_ko_review.jsonl"))
    args = parser.parse_args()
    
    pre_populate_cache(args.input)
