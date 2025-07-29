#!/usr/bin/env python3
"""
Script de nettoyage pour supprimer les anciens messages de rappel de scènes inactives.
Ce script peut être exécuté manuellement pour nettoyer les messages datant du 11/07/2025.
"""

import os
import sys
import asyncio
import discord
from discord.ext import commands
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime, timedelta
import logging

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
NOTIFICATION_CHANNEL_ID = 1380704586016362626  # Salon de notification
TARGET_DATE = datetime(2025, 7, 11, 19, 11)  # Date des messages à supprimer

async def cleanup_old_reminder_messages():
    """Nettoie les anciens messages de rappel datant du 11/07/2025."""
    
    # Configuration du bot
    intents = discord.Intents.default()
    intents.message_content = True
    
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        logger.info(f'🤖 Bot connecté en tant que {bot.user.name}')
        
        try:
            # Récupérer le salon de notification
            notification_channel = bot.get_channel(NOTIFICATION_CHANNEL_ID)
            if not notification_channel:
                logger.error(f"❌ Salon de notification {NOTIFICATION_CHANNEL_ID} non trouvé")
                return
            
            logger.info(f"📋 Recherche des messages de rappel dans {notification_channel.name}")
            
            # Configuration Google Sheets
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            try:
                creds = Credentials.from_service_account_info(
                    json.loads(os.getenv('SERVICE_ACCOUNT_JSON')),
                    scopes=scopes
                )
                gspread_client = gspread.authorize(creds)
                spreadsheet = gspread_client.open_by_key(os.getenv('GOOGLE_SHEET_ID_VALIDATION'))
                
                # Accéder à la feuille des messages de ping
                try:
                    ping_sheet = spreadsheet.worksheet("Ping Messages")
                except gspread.exceptions.WorksheetNotFound:
                    logger.warning("⚠️ Feuille 'Ping Messages' non trouvée")
                    ping_sheet = None
                    
            except Exception as e:
                logger.error(f"❌ Erreur lors de la configuration Google Sheets: {e}")
                ping_sheet = None
            
            # Rechercher les messages de rappel récents
            messages_found = 0
            messages_deleted = 0
            
            # Rechercher dans l'historique du salon (derniers 100 messages)
            async for message in notification_channel.history(limit=100):
                # Vérifier si c'est un message de rappel de scène inactive
                if (message.author == bot.user and 
                    message.embeds and 
                    len(message.embeds) > 0 and
                    "Scène inactive" in str(message.embeds[0].title or "")):
                    
                    messages_found += 1
                    message_date = message.created_at.replace(tzinfo=None)
                    
                    # Vérifier si le message date d'avant aujourd'hui
                    if message_date < datetime.now() - timedelta(hours=1):
                        logger.info(f"🗑️ Suppression du message de rappel: {message.id} (créé le {message_date})")
                        
                        try:
                            await message.delete()
                            messages_deleted += 1
                            
                            # Supprimer aussi de la feuille Google Sheets si elle existe
                            if ping_sheet:
                                try:
                                    all_values = ping_sheet.get_all_values()
                                    for idx, row in enumerate(all_values[1:], start=2):
                                        if len(row) >= 1 and row[0] == str(message.id):
                                            ping_sheet.delete_rows(idx)
                                            logger.info(f"🗑️ Supprimé de Google Sheets: ligne {idx}")
                                            break
                                except Exception as e:
                                    logger.error(f"❌ Erreur lors de la suppression de Google Sheets: {e}")
                                    
                        except discord.NotFound:
                            logger.info(f"ℹ️ Message {message.id} déjà supprimé")
                        except discord.Forbidden:
                            logger.error(f"❌ Permissions insuffisantes pour supprimer le message {message.id}")
                        except Exception as e:
                            logger.error(f"❌ Erreur lors de la suppression du message {message.id}: {e}")
                    else:
                        logger.info(f"ℹ️ Message récent conservé: {message.id} (créé le {message_date})")
            
            # Nettoyer aussi la feuille Google Sheets des entrées orphelines
            if ping_sheet:
                logger.info("🧹 Nettoyage de la feuille Google Sheets...")
                try:
                    all_values = ping_sheet.get_all_values()
                    rows_to_delete = []
                    
                    for idx, row in enumerate(all_values[1:], start=2):
                        if len(row) >= 3 and row[0] and row[2]:
                            try:
                                message_id = int(row[0])
                                timestamp = row[2]
                                message_time = datetime.fromisoformat(timestamp)
                                
                                # Supprimer les entrées de plus de 2 jours
                                if (datetime.now() - message_time).total_seconds() > 172800:  # 48h
                                    rows_to_delete.append(idx)
                                    logger.info(f"🗑️ Marqué pour suppression: ligne {idx} (message {message_id})")
                                    
                            except (ValueError, TypeError) as e:
                                logger.warning(f"⚠️ Ligne invalide: {row} - {e}")
                                rows_to_delete.append(idx)
                    
                    # Supprimer les lignes en commençant par la fin
                    for row_idx in reversed(rows_to_delete):
                        try:
                            ping_sheet.delete_rows(row_idx)
                        except Exception as e:
                            logger.error(f"❌ Erreur lors de la suppression de la ligne {row_idx}: {e}")
                    
                    if rows_to_delete:
                        logger.info(f"🧹 Nettoyé {len(rows_to_delete)} entrées de la feuille Google Sheets")
                        
                except Exception as e:
                    logger.error(f"❌ Erreur lors du nettoyage de Google Sheets: {e}")
            
            logger.info("✅ Nettoyage terminé!")
            logger.info(f"📊 Résumé:")
            logger.info(f"   - Messages de rappel trouvés: {messages_found}")
            logger.info(f"   - Messages supprimés: {messages_deleted}")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du nettoyage: {e}")
        finally:
            await bot.close()
    
    # Démarrer le bot
    try:
        await bot.start(os.getenv('DISCORD_TOKEN'))
    except Exception as e:
        logger.error(f"❌ Erreur lors du démarrage du bot: {e}")

if __name__ == "__main__":
    # Vérifier les variables d'environnement
    required_vars = ['DISCORD_TOKEN', 'SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_ID_VALIDATION']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Variables d'environnement manquantes : {', '.join(missing_vars)}")
        import sys
        sys.exit(1)
    else:
        asyncio.run(cleanup_old_reminder_messages())
