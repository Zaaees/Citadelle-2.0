
import os
import sys
import logging
import asyncio
import discord
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Ajout du chemin racine pour les imports
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
sys.path.insert(0, ROOT_PATH)

# Config logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UserCacheUpdate")

# Charger les variables d'environnement
env_path = os.path.join(os.getcwd(), '.env')
load_dotenv(dotenv_path=env_path)

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SERVICE_ACCOUNT_INFO = os.getenv('SERVICE_ACCOUNT_JSON')
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID_CARTES')

if not DISCORD_TOKEN or not SERVICE_ACCOUNT_INFO or not GOOGLE_SHEET_ID:
    logger.error("❌ Variables d'environnement manquantes (DISCORD_TOKEN, SERVICE_ACCOUNT_JSON, GOOGLE_SHEET_ID)")
    sys.exit(1)

import json
creds_dict = json.loads(SERVICE_ACCOUNT_INFO)
if 'private_key' in creds_dict:
    creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

# Initialisation Discord
intents = discord.Intents.default()
intents.members = True
bot = discord.Client(intents=intents)

async def update_cache():
    try:
        logger.info("📂 Ouverture des feuilles Google Sheets...")
        
        # 1. Lire la feuille Cards (1ère feuille)
        sheet_cards = spreadsheet.get_worksheet(0)
        logger.info(f"✅ Feuille Cards trouvée: {sheet_cards.title}")
        
        all_cards = sheet_cards.get_all_values()
        
        # 2. Extraire tous les user_ids uniques
        user_ids = set()
        for row in all_cards[1:]:  # Skip header
            for cell in row[2:]:   # Skip categorie/nom
                if cell and ':' in cell:
                    try:
                        uid = cell.split(':')[0].strip()
                        if uid.isdigit():
                            user_ids.add(uid)
                    except:
                        pass
        
        logger.info(f"🔍 {len(user_ids)} utilisateurs uniques trouvés dans les cartes.")

        # 3. Lire la feuille UserCache
        try:
            sheet_cache = spreadsheet.worksheet("UserCache")
        except:
            logger.info("⚠️ Feuille UserCache absente, création...")
            sheet_cache = spreadsheet.add_worksheet(title="UserCache", rows="1000", cols="4")
            sheet_cache.append_row(["user_id", "username", "global_name", "last_seen"])

        existing_cache = sheet_cache.get_all_values()
        cached_ids = set()
        
        # Mapping existant pour vérification
        # row index (1-based) -> user_id
        cache_map = {} 
        
        for i, row in enumerate(existing_cache[1:], start=2):
            if row and row[0]:
                uid = row[0].strip()
                cached_ids.add(uid)
                cache_map[uid] = i

        # 4. Identifier les IDs manquants
        missing_ids = user_ids - cached_ids
        logger.info(f"🔍 {len(missing_ids)} IDs manquants dans le cache.")
        
        if not missing_ids:
            logger.info("✅ Cache déjà à jour.")
            await bot.close()
            return

        # 5. Récupérer les infos Discord
        updates = []
        batch_size = 0
        
        logger.info("🚀 Récupération des infos Discord...")
        
        for uid in missing_ids:
            try:
                user = await bot.fetch_user(int(uid))
                username = user.name
                global_name = user.global_name or username
                
                updates.append([uid, username, global_name, "Script Update"])
                logger.info(f"Found: {uid} -> {username}")
                
            except discord.NotFound:
                logger.warning(f"❌ Utilisateur non trouvé sur Discord: {uid}")
                updates.append([uid, f"Unknown_{uid}", "Unknown", "Not Found"])
            except Exception as e:
                logger.error(f"❌ Erreur pour {uid}: {e}")
                
            await asyncio.sleep(0.5) # Rate limit protection

        # 6. Sauvegarder dans Sheet
        if updates:
            logger.info(f"💾 Sauvegarde de {len(updates)} nouvelles entrées...")
            for update in updates:
                sheet_cache.append_row(update)
                await asyncio.sleep(0.5) # Write limit safety
            
        logger.info("✅ Mise à jour terminée !")
        
    except Exception as e:
        logger.error(f"🔥 Erreur critique: {e}")
        import traceback
        traceback.print_exc()
    
    await bot.close()

@bot.event
async def on_ready():
    logger.info(f"🤖 Connecté en tant que {bot.user}")
    await update_cache()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
