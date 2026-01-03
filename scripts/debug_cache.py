
import sys
import os
import logging
import asyncio

# Setup path
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../Site/backend'))
sys.path.insert(0, ROOT_PATH)

# Also add the root for cogs import
ROOT_ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
sys.path.insert(0, ROOT_ROOT_PATH)

# Load backend specific .env
from dotenv import load_dotenv
backend_env = os.path.join(ROOT_PATH, '.env')
if os.path.exists(backend_env):
    print(f"Loading env from {backend_env}")
    load_dotenv(backend_env)
else:
    print(f"❌ Backend .env not found at {backend_env}")

from app.services.cards_service import card_system
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugCache")

def main():
    logger.info("Initializing CardSystem...")
    try:
        card_system.initialize()
    except Exception as e:
        logger.error(f"Init failed: {e}")
        return

    user_id = 350249452810
    logger.info(f"Checking cache for user_id: {user_id}")
    
    # Check cache directly
    if hasattr(card_system, 'local_user_cache'):
        val = card_system.local_user_cache.get(str(user_id))
        logger.info(f"Direct cache access for '{user_id}': {val}")
        
        # Dump some cache keys to see what's in there
        keys = list(card_system.local_user_cache.keys())
        logger.info(f"Total keys in cache: {len(keys)}")
        logger.info(f"Sample keys: {keys[:5]}")
        
        if str(user_id) in card_system.local_user_cache:
             logger.info("✅ Key exists in cache!")
        else:
             logger.info("❌ Key NOT in cache!")
    else:
        logger.info("❌ No local_user_cache found!")

    # Check via method
    username = card_system.get_username(user_id)
    logger.info(f"get_username({user_id}) returned: {username}")

if __name__ == "__main__":
    main()
