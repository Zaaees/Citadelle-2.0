
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
env_path = os.path.join(ROOT_PATH, '.env')
load_dotenv(dotenv_path=env_path)

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SERVICE_ACCOUNT_INFO = os.getenv('SERVICE_ACCOUNT_JSON')
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID_CARTES') or os.getenv('GOOGLE_SHEET_ID')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FixCache")

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
    sheet_cache = spreadsheet.worksheet("UserCache")

    records = sheet_cache.get_all_values()
    
    # Map full ID to data
    full_id_map = {row[0]: row for row in records if len(row) > 1}
    
    # ID à corriger (Tronqué -> Full)
    # On cherche l'ID full qui commence par le tronqué ou lui ressemble
    target_truncated = "350249452810" 
    
    found_full = None
    for full_id in full_id_map:
        if full_id.startswith(target_truncated):
            found_full = full_id
            break
            
    if found_full:
        data = full_id_map[found_full]
        username = data[1]
        global_name = data[2] if len(data) > 2 else ""
        last_seen = data[3] if len(data) > 3 else ""
        
        logger.info(f"MATCH: {target_truncated} semble être {found_full} ({username})")
        
        # Vérifier si l'entrée tronquée existe déjà
        if target_truncated in full_id_map:
            logger.info("L'entrée tronquée existe déjà.")
        else:
            logger.info(f"Ajout de l'alias {target_truncated} -> {username}")
            sheet_cache.append_row([target_truncated, username, global_name, last_seen])
            logger.info("✅ Correction appliquée !")
    else:
        logger.warning(f"Aucun ID complet trouvé correspondant à {target_truncated}")

if __name__ == "__main__":
    main()
