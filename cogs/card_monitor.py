"""
Cog de surveillance quotidienne des données Google Sheets pour les cartes.
Surveille les ajouts/suppressions de cartes et envoie un rapport quotidien.
"""

import discord
from discord.ext import commands, tasks
import os
import json
import logging
import pytz
from datetime import datetime, time as dt_time
from typing import Dict, List, Tuple, Optional, Set
import gspread
from google.oauth2.service_account import Credentials


class CardMonitor(commands.Cog):
    """Surveillance quotidienne des changements dans les données de cartes."""
    
    def __init__(self, bot):
        self.bot = bot
        self.paris_tz = pytz.timezone('Europe/Paris')
        self.notification_channel_id = 1230946716849799381
        
        # Configuration Google Sheets
        self.setup_google_sheets()
        
        # Stockage des snapshots
        self.snapshot_file = "card_snapshots.json"
        self.last_snapshot = self.load_last_snapshot()
        
        # Démarrer la tâche de surveillance
        self.daily_monitor.start()
        
        logging.info("[CARD_MONITOR] Cog de surveillance des cartes initialisé")
    
    def setup_google_sheets(self):
        """Configure l'accès à Google Sheets."""
        try:
            service_account_info = eval(os.getenv('SERVICE_ACCOUNT_JSON'))
            creds = Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self.gspread_client = gspread.authorize(creds)
            self.spreadsheet = self.gspread_client.open_by_key(os.getenv('GOOGLE_SHEET_ID_CARTES'))
            self.sheet_cards = self.spreadsheet.sheet1
            logging.info("[CARD_MONITOR] Connexion Google Sheets établie")
        except Exception as e:
            logging.error(f"[CARD_MONITOR] Erreur lors de la configuration Google Sheets: {e}")
            self.gspread_client = None
            self.sheet_cards = None
    
    def load_last_snapshot(self) -> Optional[Dict]:
        """Charge le dernier snapshot sauvegardé."""
        try:
            if os.path.exists(self.snapshot_file):
                with open(self.snapshot_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logging.error(f"[CARD_MONITOR] Erreur lors du chargement du snapshot: {e}")
        return None
    
    def save_snapshot(self, snapshot: Dict):
        """Sauvegarde un snapshot des données."""
        try:
            with open(self.snapshot_file, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            logging.info("[CARD_MONITOR] Snapshot sauvegardé")
        except Exception as e:
            logging.error(f"[CARD_MONITOR] Erreur lors de la sauvegarde du snapshot: {e}")
    
    def get_current_data(self) -> Optional[Dict]:
        """Récupère les données actuelles du Google Sheet."""
        if not self.sheet_cards:
            return None
        
        try:
            all_rows = self.sheet_cards.get_all_values()
            if not all_rows:
                return None
            
            # Créer un dictionnaire des données actuelles
            current_data = {
                'timestamp': datetime.now(self.paris_tz).isoformat(),
                'cards': {}
            }
            
            # Parser les données (ignorer la première ligne si c'est un header)
            start_row = 1 if all_rows and all_rows[0] and all_rows[0][0].lower() in ['category', 'catégorie'] else 0
            
            for row in all_rows[start_row:]:
                if len(row) < 3 or not row[0] or not row[1]:
                    continue
                
                category, name = row[0].strip(), row[1].strip()
                card_key = f"{category}|{name}"
                
                # Parser les données utilisateurs
                user_data = {}
                for cell in row[2:]:
                    if not cell or ':' not in cell:
                        continue
                    try:
                        user_id, count = cell.split(':', 1)
                        user_id = user_id.strip()
                        count = int(count.strip())
                        if count > 0:
                            user_data[user_id] = count
                    except (ValueError, IndexError):
                        continue
                
                if user_data:  # Seulement si la carte a des propriétaires
                    current_data['cards'][card_key] = {
                        'category': category,
                        'name': name,
                        'users': user_data
                    }
            
            return current_data
            
        except Exception as e:
            logging.error(f"[CARD_MONITOR] Erreur lors de la récupération des données: {e}")
            return None
    
    async def get_user_display_name(self, user_id: str) -> str:
        """Récupère le nom d'affichage d'un utilisateur à partir de son ID."""
        try:
            user_id_int = int(user_id)
            
            # Essayer d'abord avec get_user (cache)
            user = self.bot.get_user(user_id_int)
            if user:
                return user.display_name
            
            # Si pas en cache, essayer avec fetch_user (API)
            try:
                user = await self.bot.fetch_user(user_id_int)
                return user.display_name
            except discord.NotFound:
                return f"Utilisateur#{user_id[-4:]}"  # Derniers 4 chiffres
            
        except (ValueError, discord.HTTPException):
            return f"Utilisateur#{user_id[-4:] if len(user_id) >= 4 else user_id}"
    
    @tasks.loop(time=dt_time(hour=0, minute=0, tzinfo=pytz.timezone('Europe/Paris')))
    async def daily_monitor(self):
        """Tâche quotidienne de surveillance à minuit (heure de Paris)."""
        logging.info("[CARD_MONITOR] Début de la surveillance quotidienne")
        
        channel = self.bot.get_channel(self.notification_channel_id)
        if not channel:
            logging.error(f"[CARD_MONITOR] Canal de notification non trouvé: {self.notification_channel_id}")
            return
        
        try:
            # Récupérer les données actuelles
            current_data = self.get_current_data()
            
            if not current_data:
                # Erreur d'accès à Google Sheets
                embed = discord.Embed(
                    title="⚠️ Erreur de surveillance des cartes",
                    description="Impossible d'accéder aux données Google Sheets pour la surveillance quotidienne.",
                    color=0xe74c3c,
                    timestamp=datetime.now(self.paris_tz)
                )
                await channel.send(embed=embed)
                return
            
            # Comparer avec le snapshot précédent
            if self.last_snapshot:
                await self.compare_and_report(channel, self.last_snapshot, current_data)
            else:
                # Premier snapshot, juste informer
                embed = discord.Embed(
                    title="📊 Surveillance des cartes initialisée",
                    description="Premier snapshot des données de cartes créé. La surveillance quotidienne commencera demain.",
                    color=0x3498db,
                    timestamp=datetime.now(self.paris_tz)
                )
                total_cards = len(current_data['cards'])
                embed.add_field(name="Cartes actuelles", value=str(total_cards), inline=True)
                await channel.send(embed=embed)
            
            # Sauvegarder le nouveau snapshot
            self.last_snapshot = current_data
            self.save_snapshot(current_data)
            
        except Exception as e:
            logging.error(f"[CARD_MONITOR] Erreur dans la surveillance quotidienne: {e}")
            embed = discord.Embed(
                title="❌ Erreur de surveillance",
                description=f"Une erreur s'est produite lors de la surveillance quotidienne:\n```{str(e)}```",
                color=0xe74c3c,
                timestamp=datetime.now(self.paris_tz)
            )
            await channel.send(embed=embed)
    
    @daily_monitor.before_loop
    async def before_daily_monitor(self):
        """Attendre que le bot soit prêt avant de démarrer la surveillance."""
        await self.bot.wait_until_ready()
        logging.info("[CARD_MONITOR] Bot prêt, surveillance quotidienne programmée")

    async def compare_and_report(self, channel: discord.TextChannel, old_data: Dict, new_data: Dict):
        """Compare deux snapshots et génère un rapport des changements."""
        old_cards = old_data.get('cards', {})
        new_cards = new_data.get('cards', {})

        # Détecter les changements
        added_cards = []
        removed_cards = []
        modified_cards = []

        # Cartes ajoutées
        for card_key, card_data in new_cards.items():
            if card_key not in old_cards:
                added_cards.append(card_data)

        # Cartes supprimées
        for card_key, card_data in old_cards.items():
            if card_key not in new_cards:
                removed_cards.append(card_data)

        # Cartes modifiées (changements de quantités)
        for card_key in set(old_cards.keys()) & set(new_cards.keys()):
            old_users = old_cards[card_key]['users']
            new_users = new_cards[card_key]['users']

            if old_users != new_users:
                modified_cards.append({
                    'card': new_cards[card_key],
                    'old_users': old_users,
                    'new_users': new_users
                })

        # Générer le rapport
        await self.send_daily_report(channel, added_cards, removed_cards, modified_cards, old_data, new_data)

    async def send_daily_report(self, channel: discord.TextChannel, added_cards: List,
                               removed_cards: List, modified_cards: List, old_data: Dict, new_data: Dict):
        """Envoie le rapport quotidien des changements."""

        # Embed principal avec résumé
        embed = discord.Embed(
            title="📊 Rapport quotidien - Surveillance des cartes",
            color=0x3498db,
            timestamp=datetime.now(self.paris_tz)
        )

        # Statistiques générales
        old_total = len(old_data.get('cards', {}))
        new_total = len(new_data.get('cards', {}))
        total_change = new_total - old_total

        embed.add_field(
            name="📈 Statistiques",
            value=f"**Total cartes:** {new_total} ({total_change:+d})\n"
                  f"**Cartes ajoutées:** {len(added_cards)}\n"
                  f"**Cartes supprimées:** {len(removed_cards)}\n"
                  f"**Cartes modifiées:** {len(modified_cards)}",
            inline=False
        )

        # Si aucun changement
        if not added_cards and not removed_cards and not modified_cards:
            embed.add_field(
                name="✅ Aucun changement",
                value="Aucune modification détectée depuis hier.",
                inline=False
            )
            await channel.send(embed=embed)
            return

        await channel.send(embed=embed)

        # Détails des cartes ajoutées
        if added_cards:
            await self.send_added_cards_report(channel, added_cards)

        # Détails des cartes supprimées
        if removed_cards:
            await self.send_removed_cards_report(channel, removed_cards)

        # Détails des cartes modifiées
        if modified_cards:
            await self.send_modified_cards_report(channel, modified_cards)

    async def send_added_cards_report(self, channel: discord.TextChannel, added_cards: List):
        """Envoie le rapport des cartes ajoutées."""
        embed = discord.Embed(
            title="➕ Cartes ajoutées",
            color=0x27ae60,
            timestamp=datetime.now(self.paris_tz)
        )

        # Grouper par catégorie
        by_category = {}
        for card in added_cards:
            category = card['category']
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(card)

        for category, cards in by_category.items():
            card_list = []
            for card in cards:
                name = card['name'].removesuffix('.png')
                owners = []
                for user_id, count in card['users'].items():
                    user_name = await self.get_user_display_name(user_id)
                    if count > 1:
                        owners.append(f"{user_name} (×{count})")
                    else:
                        owners.append(user_name)

                owners_text = ", ".join(owners)
                card_list.append(f"**{name}** - {owners_text}")

            # Diviser en chunks si trop long
            card_text = "\n".join(card_list)
            if len(card_text) > 1000:
                # Diviser en plusieurs champs
                chunks = []
                current_chunk = []
                current_length = 0

                for card_line in card_list:
                    if current_length + len(card_line) + 1 > 1000:
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [card_line]
                        current_length = len(card_line)
                    else:
                        current_chunk.append(card_line)
                        current_length += len(card_line) + 1

                if current_chunk:
                    chunks.append("\n".join(current_chunk))

                for i, chunk in enumerate(chunks):
                    field_name = f"{category}" if i == 0 else f"{category} (suite {i+1})"
                    embed.add_field(name=field_name, value=chunk, inline=False)
            else:
                embed.add_field(name=category, value=card_text, inline=False)

        await channel.send(embed=embed)

    async def send_removed_cards_report(self, channel: discord.TextChannel, removed_cards: List):
        """Envoie le rapport des cartes supprimées."""
        embed = discord.Embed(
            title="➖ Cartes supprimées",
            color=0xe74c3c,
            timestamp=datetime.now(self.paris_tz)
        )

        # Grouper par catégorie
        by_category = {}
        for card in removed_cards:
            category = card['category']
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(card)

        for category, cards in by_category.items():
            card_list = []
            for card in cards:
                name = card['name'].removesuffix('.png')
                owners = []
                for user_id, count in card['users'].items():
                    user_name = await self.get_user_display_name(user_id)
                    if count > 1:
                        owners.append(f"{user_name} (×{count})")
                    else:
                        owners.append(user_name)

                owners_text = ", ".join(owners)
                card_list.append(f"**{name}** - {owners_text}")

            card_text = "\n".join(card_list)
            if len(card_text) > 1000:
                # Diviser en chunks si trop long
                chunks = []
                current_chunk = []
                current_length = 0

                for card_line in card_list:
                    if current_length + len(card_line) + 1 > 1000:
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [card_line]
                        current_length = len(card_line)
                    else:
                        current_chunk.append(card_line)
                        current_length += len(card_line) + 1

                if current_chunk:
                    chunks.append("\n".join(current_chunk))

                for i, chunk in enumerate(chunks):
                    field_name = f"{category}" if i == 0 else f"{category} (suite {i+1})"
                    embed.add_field(name=field_name, value=chunk, inline=False)
            else:
                embed.add_field(name=category, value=card_text, inline=False)

        await channel.send(embed=embed)

    async def send_modified_cards_report(self, channel: discord.TextChannel, modified_cards: List):
        """Envoie le rapport des cartes modifiées."""
        embed = discord.Embed(
            title="🔄 Cartes modifiées",
            color=0xf39c12,
            timestamp=datetime.now(self.paris_tz)
        )

        # Grouper par catégorie
        by_category = {}
        for card_data in modified_cards:
            category = card_data['card']['category']
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(card_data)

        for category, cards in by_category.items():
            card_list = []
            for card_data in cards:
                card = card_data['card']
                old_users = card_data['old_users']
                new_users = card_data['new_users']

                name = card['name'].removesuffix('.png')

                # Analyser les changements
                changes = []
                all_users = set(old_users.keys()) | set(new_users.keys())

                for user_id in all_users:
                    old_count = old_users.get(user_id, 0)
                    new_count = new_users.get(user_id, 0)

                    if old_count != new_count:
                        user_name = await self.get_user_display_name(user_id)
                        if old_count == 0:
                            changes.append(f"{user_name}: +{new_count}")
                        elif new_count == 0:
                            changes.append(f"{user_name}: -{old_count}")
                        else:
                            diff = new_count - old_count
                            changes.append(f"{user_name}: {diff:+d} ({old_count}→{new_count})")

                changes_text = ", ".join(changes)
                card_list.append(f"**{name}** - {changes_text}")

            card_text = "\n".join(card_list)
            if len(card_text) > 1000:
                # Diviser en chunks si trop long
                chunks = []
                current_chunk = []
                current_length = 0

                for card_line in card_list:
                    if current_length + len(card_line) + 1 > 1000:
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [card_line]
                        current_length = len(card_line)
                    else:
                        current_chunk.append(card_line)
                        current_length += len(card_line) + 1

                if current_chunk:
                    chunks.append("\n".join(current_chunk))

                for i, chunk in enumerate(chunks):
                    field_name = f"{category}" if i == 0 else f"{category} (suite {i+1})"
                    embed.add_field(name=field_name, value=chunk, inline=False)
            else:
                embed.add_field(name=category, value=card_text, inline=False)

        await channel.send(embed=embed)

    # ========== COMMANDES DE GESTION ==========

    @commands.command(name="monitor_status", help="Affiche le statut de la surveillance des cartes")
    @commands.has_permissions(administrator=True)
    async def monitor_status(self, ctx):
        """Affiche le statut actuel de la surveillance."""
        embed = discord.Embed(
            title="📊 Statut de la surveillance des cartes",
            color=0x3498db,
            timestamp=datetime.now(self.paris_tz)
        )

        # Statut de la tâche
        if self.daily_monitor.is_running():
            embed.add_field(
                name="🟢 Surveillance active",
                value="La surveillance quotidienne est en cours d'exécution.",
                inline=False
            )
        else:
            embed.add_field(
                name="🔴 Surveillance inactive",
                value="La surveillance quotidienne n'est pas active.",
                inline=False
            )

        # Prochaine exécution
        if self.daily_monitor.next_iteration:
            next_run = self.daily_monitor.next_iteration.astimezone(self.paris_tz)
            embed.add_field(
                name="⏰ Prochaine surveillance",
                value=next_run.strftime("%d/%m/%Y à %H:%M (heure de Paris)"),
                inline=True
            )

        # Dernier snapshot
        if self.last_snapshot:
            last_time = datetime.fromisoformat(self.last_snapshot['timestamp'])
            embed.add_field(
                name="📸 Dernier snapshot",
                value=last_time.strftime("%d/%m/%Y à %H:%M"),
                inline=True
            )
            embed.add_field(
                name="📋 Cartes surveillées",
                value=str(len(self.last_snapshot.get('cards', {}))),
                inline=True
            )
        else:
            embed.add_field(
                name="📸 Dernier snapshot",
                value="Aucun snapshot disponible",
                inline=False
            )

        # Statut Google Sheets
        if self.sheet_cards:
            embed.add_field(
                name="🟢 Google Sheets",
                value="Connexion établie",
                inline=True
            )
        else:
            embed.add_field(
                name="🔴 Google Sheets",
                value="Connexion échouée",
                inline=True
            )

        await ctx.send(embed=embed)

    @commands.command(name="monitor_test", help="Teste la surveillance manuellement")
    @commands.has_permissions(administrator=True)
    async def monitor_test(self, ctx):
        """Effectue un test manuel de la surveillance."""
        await ctx.send("🔍 Test de surveillance en cours...")

        try:
            # Simuler la surveillance quotidienne
            channel = self.bot.get_channel(self.notification_channel_id)
            if not channel:
                await ctx.send(f"❌ Canal de notification non trouvé: {self.notification_channel_id}")
                return

            current_data = self.get_current_data()
            if not current_data:
                await ctx.send("❌ Impossible de récupérer les données Google Sheets")
                return

            if self.last_snapshot:
                await self.compare_and_report(channel, self.last_snapshot, current_data)
                await ctx.send("✅ Test terminé - rapport envoyé dans le canal de surveillance")
            else:
                await ctx.send("⚠️ Aucun snapshot précédent disponible pour comparaison")

        except Exception as e:
            await ctx.send(f"❌ Erreur lors du test: {str(e)}")
            logging.error(f"[CARD_MONITOR] Erreur lors du test manuel: {e}")

    @commands.command(name="monitor_snapshot", help="Force la création d'un nouveau snapshot")
    @commands.has_permissions(administrator=True)
    async def monitor_snapshot(self, ctx):
        """Force la création d'un nouveau snapshot."""
        await ctx.send("📸 Création d'un nouveau snapshot...")

        try:
            current_data = self.get_current_data()
            if not current_data:
                await ctx.send("❌ Impossible de récupérer les données Google Sheets")
                return

            self.last_snapshot = current_data
            self.save_snapshot(current_data)

            total_cards = len(current_data['cards'])
            await ctx.send(f"✅ Nouveau snapshot créé avec {total_cards} cartes")

        except Exception as e:
            await ctx.send(f"❌ Erreur lors de la création du snapshot: {str(e)}")
            logging.error(f"[CARD_MONITOR] Erreur lors de la création manuelle du snapshot: {e}")

    def cog_unload(self):
        """Nettoie les ressources lors du déchargement du cog."""
        self.daily_monitor.cancel()
        logging.info("[CARD_MONITOR] Cog de surveillance des cartes déchargé")


async def setup(bot):
    """Fonction de setup pour charger le cog."""
    await bot.add_cog(CardMonitor(bot))
