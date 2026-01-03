
import os
import sys
import logging
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# Setup path
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
sys.path.insert(0, ROOT_PATH)

# Load env including backend .env for SHEET_ID if needed, but we use root mostly?
# Actually use root .env logic from update_user_names.py as that worked
env_path = os.path.join(ROOT_PATH, '.env')
load_dotenv(dotenv_path=env_path)

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SERVICE_ACCOUNT_INFO = os.getenv('SERVICE_ACCOUNT_JSON')
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID_CARTES') or os.getenv('GOOGLE_SHEET_ID')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CheckSheet")

def main():
    if not SERVICE_ACCOUNT_INFO or not GOOGLE_SHEET_ID:
        logger.error("Missing config")
        return

    creds_dict = json.loads(SERVICE_ACCOUNT_INFO)
    if 'private_key' in creds_dict:
        creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')

    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    
    try:
        sheet_cache = spreadsheet.worksheet("UserCache")
    except:
        logger.error("UserCache sheet not found")
        return

    records = sheet_cache.get_all_values()
    target_id = "350249452810"
    
    logger.info(f"Scanning {len(records)} rows for {target_id}...")
    found = False
    for row in records:
        if row and row[0] == target_id:
            logger.info(f"✅ FOUND: {row}")
            found = True
            break
            
    if not found:
        logger.info("❌ ID NOT FOUND in UserCache sheet")
        # Print all ids to see if there's a close match or format issue
        ids = [r[0] for r in records if r]
        logger.info(f"Available IDs: {ids}")

if __name__ == "__main__":
    main()
