"""
Gestion du forum des cartes.
Gère la création de threads, le posting des cartes découvertes, etc.
"""

import asyncio
import logging
import discord
import io
from typing import Dict, Optional, List, Tuple

from .config import CARD_FORUM_CHANNEL_ID, ALL_CATEGORIES
from .discovery import DiscoveryManager


class ForumManager:
    """Gestionnaire du forum des cartes."""

    def __init__(self, bot, discovery_manager: DiscoveryManager):
        self.bot = bot
        self.discovery_manager = discovery_manager
        self.category_threads = {}  # Cache for category thread IDs
        self.thread_cache_time = 0

        # Couleurs par catégorie pour les embeds
        self.category_colors = {
            "Secrète": 0x9b59b6,      # Violet
            "Fondateur": 0xe74c3c,    # Rouge
            "Historique": 0xf39c12,   # Orange
            "Maître": 0x3498db,       # Bleu
            "Black Hole": 0x2c3e50,   # Noir/Gris foncé
            "Architectes": 0x1abc9c,  # Turquoise
            "Professeurs": 0x27ae60,  # Vert
            "Autre": 0x95a5a6,        # Gris
            "Élèves": 0xf1c40f,       # Jaune
            "Full": 0xfd79a8          # Rose
        }
    
    def get_all_card_categories(self) -> List[str]:
        """Retourne la liste complète des catégories de cartes."""
        return ALL_CATEGORIES.copy()

    def get_category_stats(self, category: str, cards_by_category: dict = None, upgrade_cards_by_category: dict = None) -> dict:
        """
        Retourne les statistiques d'une catégorie spécifique.

        Args:
            category: Nom de la catégorie
            cards_by_category: Dictionnaire des cartes normales par catégorie
            upgrade_cards_by_category: Dictionnaire des cartes Full par catégorie

        Returns:
            dict: Statistiques avec total_available, discovered, missing
        """
        # Récupérer toutes les cartes disponibles dans cette catégorie
        available_cards = set()

        # Cartes normales
        if cards_by_category and category in cards_by_category:
            for card_file in cards_by_category[category]:
                card_name = card_file['name'].removesuffix('.png')
                available_cards.add(card_name)

        # Cartes Full
        if upgrade_cards_by_category and category in upgrade_cards_by_category:
            for card_file in upgrade_cards_by_category[category]:
                card_name = card_file['name'].removesuffix('.png')
                available_cards.add(card_name)

        # Récupérer les cartes découvertes dans cette catégorie
        discovered_cards = set()
        discovered_cards_data = self.discovery_manager.get_discovered_cards()

        for cat, name in discovered_cards_data:
            if cat == category:
                discovered_cards.add(name)

        # Calculer les statistiques
        total_available = len(available_cards)
        discovered_count = len(discovered_cards)
        missing_count = total_available - discovered_count

        return {
            'category': category,
            'total_available': total_available,
            'discovered': discovered_count,
            'missing': missing_count
        }
    
    async def get_or_create_category_thread(self, forum_channel: discord.ForumChannel, 
                                          category: str) -> Optional[discord.Thread]:
        """
        Récupère ou crée un thread pour une catégorie donnée.
        
        Args:
            forum_channel: Canal forum Discord
            category: Nom de la catégorie
        
        Returns:
            discord.Thread: Thread de la catégorie ou None si erreur
        """
        try:
            # Vérifier le cache
            if category in self.category_threads:
                thread_id = self.category_threads[category]
                try:
                    # Utiliser bot.get_channel pour récupérer le thread par son ID
                    thread = self.bot.get_channel(thread_id)
                    if thread and isinstance(thread, discord.Thread) and not thread.archived:
                        return thread
                    # Si pas dans le cache, essayer de le fetch
                    if not thread:
                        thread = await self.bot.fetch_channel(thread_id)
                        if thread and isinstance(thread, discord.Thread) and not thread.archived:
                            return thread
                except (discord.NotFound, discord.Forbidden):
                    # Thread supprimé ou inaccessible, retirer du cache
                    del self.category_threads[category]
            
            # Chercher le thread existant dans les threads actifs
            for thread in forum_channel.threads:
                if thread.name == category:
                    self.category_threads[category] = thread.id
                    return thread

            # Chercher dans les threads archivés
            async for thread in forum_channel.archived_threads(limit=None):
                if thread.name == category:
                    self.category_threads[category] = thread.id
                    if thread.archived:
                        await thread.edit(archived=False)
                    return thread
            
            # Vérification finale avant création pour éviter les doublons
            # (au cas où un thread aurait été créé entre-temps)
            for thread in forum_channel.threads:
                if thread.name == category:
                    self.category_threads[category] = thread.id
                    logging.info(f"[FORUM] Thread {category} trouvé lors de la vérification finale")
                    return thread

            # Créer un nouveau thread
            stats = self.discovery_manager.get_discovery_stats()
            initial_message = self._create_category_initial_message(category, stats)

            thread = await forum_channel.create_thread(
                name=category,
                content=initial_message
            )

            self.category_threads[category] = thread.id
            logging.info(f"[FORUM] Thread créé pour la catégorie: {category}")
            return thread
            
        except Exception as e:
            logging.error(f"[FORUM] Erreur lors de la création/récupération du thread {category}: {e}")
            return None
    
    def _create_category_initial_message(self, category: str, stats: dict) -> str:
        """
        Crée le message initial d'un thread de catégorie.
        
        Args:
            category: Nom de la catégorie
            stats: Statistiques de découverte
        
        Returns:
            str: Message initial formaté
        """
        # Message de base
        message = f"🎴 **Cartes de la catégorie {category}**\n\n"
        message += "Ce thread contient toutes les cartes découvertes de cette catégorie, "
        message += "dans l'ordre chronologique de leur découverte.\n\n"
        
        # Ajouter les statistiques si disponibles
        if stats and any(stats.values()):
            message += "📊 **Progression globale:**\n"
            message += f"• Total (avec Full): {stats.get('discovered_all', 0)}/{stats.get('total_all', 0)}\n"
            message += f"• Total (sans Full): {stats.get('discovered_no_full', 0)}/{stats.get('total_no_full', 0)}\n\n"
        
        message += "---\n"
        return message

    def create_card_embed(self, name: str, category: str, discoverer_name: str, discovery_index: int, image_url: str = None) -> discord.Embed:
        """
        Crée un embed élégant pour une carte découverte.

        Args:
            name: Nom de la carte
            category: Catégorie de la carte
            discoverer_name: Nom du découvreur
            discovery_index: Index de découverte
            image_url: URL de l'image (optionnel)

        Returns:
            discord.Embed: Embed formaté pour la carte
        """
        display_name = name.removesuffix('.png')

        # Créer l'embed avec titre et catégorie
        embed = discord.Embed(
            title=f"🎴 {display_name}",
            description=f"**Catégorie:** {category}",
            color=self.category_colors.get(category, 0x95a5a6)
        )

        # Ajouter l'image si une URL est fournie
        if image_url:
            embed.set_image(url=image_url)

        # Ajouter les informations de découverte dans le footer
        # Déterminer le suffixe ordinal
        if discovery_index % 10 == 1 and discovery_index % 100 != 11:
            suffix = "ère"
        else:
            suffix = "ème"

        footer_text = f"Découvert par : {discoverer_name}\n→ {discovery_index}{suffix} carte découverte"
        embed.set_footer(text=footer_text)

        return embed

    def create_missing_cards_embed(self, category: str, stats: dict) -> discord.Embed:
        """
        Crée un embed simple pour afficher les cartes manquantes dans une catégorie.

        Args:
            category: Nom de la catégorie
            stats: Statistiques de la catégorie

        Returns:
            discord.Embed: Embed formaté pour les cartes manquantes
        """
        missing_count = stats['missing']
        total_available = stats['total_available']

        embed = discord.Embed(
            title=f"📊 Statut de la catégorie {category}",
            color=0x95a5a6  # Couleur neutre
        )

        # Description simple
        if missing_count == 0:
            embed.description = f"🎉 **Catégorie complète !**\n\nToutes les {total_available} cartes ont été découvertes."
        else:
            embed.description = f"❓ **{missing_count} cartes manquantes** sur {total_available} disponibles"

        return embed

    async def update_category_status_message(self, thread: discord.Thread, category: str,
                                           cards_by_category: dict = None, upgrade_cards_by_category: dict = None) -> bool:
        """
        Met à jour ou crée le message de statut des cartes manquantes dans un thread.

        Args:
            thread: Thread de la catégorie
            category: Nom de la catégorie
            cards_by_category: Dictionnaire des cartes normales par catégorie
            upgrade_cards_by_category: Dictionnaire des cartes Full par catégorie

        Returns:
            bool: True si succès, False sinon
        """
        try:
            # Récupérer les statistiques de la catégorie
            stats = self.get_category_stats(category, cards_by_category, upgrade_cards_by_category)

            # Si toutes les cartes sont découvertes, supprimer le message de statut s'il existe
            if stats['missing'] == 0:
                # Chercher et supprimer le message de statut existant
                async for message in thread.history(limit=50):
                    if (message.author == self.bot.user and
                        message.embeds and
                        len(message.embeds) > 0 and
                        "Statut de la catégorie" in str(message.embeds[0].title or "")):
                        try:
                            await message.delete()
                            logging.info(f"[FORUM] Message de statut supprimé pour {category} (catégorie complète)")
                        except:
                            pass
                        break
                return True

            # Créer l'embed de statut
            status_embed = self.create_missing_cards_embed(category, stats)

            # Chercher un message de statut existant
            status_message = None
            async for message in thread.history(limit=50):
                if (message.author == self.bot.user and
                    message.embeds and
                    len(message.embeds) > 0 and
                    "Statut de la catégorie" in str(message.embeds[0].title or "")):
                    status_message = message
                    break

            if status_message:
                # Mettre à jour le message existant
                await status_message.edit(embed=status_embed)
                logging.info(f"[FORUM] Message de statut mis à jour pour {category}")
            else:
                # Créer un nouveau message de statut
                await thread.send(embed=status_embed)
                logging.info(f"[FORUM] Nouveau message de statut créé pour {category}")

            return True

        except Exception as e:
            logging.error(f"[FORUM] Erreur lors de la mise à jour du statut pour {category}: {e}")
            return False
    
    async def post_card_to_forum(self, category: str, name: str, file_bytes: bytes,
                               discoverer_name: str, discovery_index: int) -> bool:
        """
        Poste une carte dans le forum.
        
        Args:
            category: Catégorie de la carte
            name: Nom de la carte
            file_bytes: Données de l'image
            discoverer_name: Nom du découvreur
            discovery_index: Index de découverte
        
        Returns:
            bool: True si le post a réussi
        """
        try:
            forum_channel = self.bot.get_channel(CARD_FORUM_CHANNEL_ID)
            if not isinstance(forum_channel, discord.ForumChannel):
                logging.error(f"[FORUM] Canal {CARD_FORUM_CHANNEL_ID} n'est pas un ForumChannel")
                return False
            
            # Obtenir ou créer le thread de catégorie
            logging.info(f"[FORUM] Recherche/création du thread pour {category}")
            thread = await self.get_or_create_category_thread(forum_channel, category)
            if not thread:
                logging.error(f"[FORUM] Impossible d'obtenir le thread pour {category}")
                return False

            logging.info(f"[FORUM] Thread trouvé/créé: {thread.name} (ID: {thread.id})")

            # Créer le fichier Discord avec un nom constant pour l'attachment
            filename = "card.png"  # Nom constant pour l'URL attachment://

            logging.info(f"[FORUM] Création du fichier Discord pour {name} ({len(file_bytes)} bytes)")
            file = discord.File(
                fp=io.BytesIO(file_bytes),
                filename=filename
            )

            # Créer l'embed avec l'URL d'attachment
            embed = self.create_card_embed(name, category, discoverer_name, discovery_index, f"attachment://{filename}")

            # Poster l'embed avec l'image attachée directement
            logging.info(f"[FORUM] Posting de l'embed avec image attachée pour {name} dans {category}")
            sent_message = await thread.send(embed=embed, file=file)
            logging.info(f"[FORUM] ✅ Carte postée automatiquement: {name} ({category}) par {discoverer_name} - Message ID: {sent_message.id}")
            return True

        except discord.HTTPException as e:
            logging.error(f"[FORUM] Erreur HTTP Discord lors du post automatique de {name}: {e}")
            return False
        except discord.Forbidden as e:
            logging.error(f"[FORUM] Permissions insuffisantes pour poster automatiquement {name}: {e}")
            return False
        except Exception as e:
            logging.error(f"[FORUM] Erreur générale lors du post automatique de {name}: {e}")
            import traceback
            logging.error(f"[FORUM] Traceback: {traceback.format_exc()}")
            return False
    
    async def initialize_forum_structure(self) -> Tuple[List[str], List[str]]:
        """
        Initialise la structure du forum avec tous les threads de catégories.
        
        Returns:
            Tuple[List[str], List[str]]: (threads_créés, threads_existants)
        """
        try:
            forum_channel = self.bot.get_channel(CARD_FORUM_CHANNEL_ID)
            if not isinstance(forum_channel, discord.ForumChannel):
                raise ValueError(f"Canal {CARD_FORUM_CHANNEL_ID} n'est pas un ForumChannel")
            
            categories = self.get_all_card_categories()
            created_threads = []
            existing_threads = []
            
            for category in categories:
                # Vérifier si le thread existe déjà
                thread_exists = False
                async for thread in forum_channel.archived_threads(limit=None):
                    if thread.name == category:
                        existing_threads.append(category)
                        self.category_threads[category] = thread.id
                        thread_exists = True
                        break
                
                if not thread_exists:
                    # Créer le thread
                    thread = await self.get_or_create_category_thread(forum_channel, category)
                    if thread:
                        created_threads.append(category)
                    
                    # Petite pause pour éviter le rate limiting
                    await asyncio.sleep(0.5)
            
            return created_threads, existing_threads
            
        except Exception as e:
            logging.error(f"[FORUM] Erreur lors de l'initialisation du forum: {e}")
            return [], []
    
    async def populate_forum_threads(self, all_files: Dict[str, List[Dict]],
                                   drive_service=None, cards_by_category: dict = None,
                                   upgrade_cards_by_category: dict = None) -> Tuple[int, int]:
        """
        Peuple les threads du forum avec toutes les cartes découvertes.

        Args:
            all_files: Dictionnaire des fichiers par catégorie
            drive_service: Service Google Drive pour télécharger les images
            cards_by_category: Dictionnaire des cartes normales par catégorie
            upgrade_cards_by_category: Dictionnaire des cartes Full par catégorie

        Returns:
            Tuple[int, int]: (cartes_postées, erreurs)
        """
        try:
            # Récupérer toutes les découvertes triées par index chronologique
            discoveries_cache = self.discovery_manager.storage.get_discoveries_cache()

            if not discoveries_cache or len(discoveries_cache) <= 1:
                return 0, 0

            # Trier par index de découverte (chronologique)
            discovery_rows = discoveries_cache[1:]  # Skip header
            discovery_rows.sort(key=lambda row: int(row[5]) if len(row) >= 6 and row[5].isdigit() else 0)

            posted_count = 0
            error_count = 0

            for row in discovery_rows:
                if len(row) < 6:
                    continue

                cat, name, discoverer_id_str, discoverer_name, timestamp, discovery_index = row
                discovery_index = int(discovery_index)

                # Trouver le fichier de la carte
                file_id = next(
                    (f['id'] for f in all_files.get(cat, []) if f['name'].removesuffix(".png") == name),
                    None
                )
                if not file_id:
                    logging.warning(f"[FORUM] Fichier non trouvé pour {name} ({cat})")
                    error_count += 1
                    continue

                # Télécharger l'image et poster dans le forum
                try:
                    if drive_service:
                        # Télécharger l'image depuis Google Drive
                        file_bytes = self._download_drive_file(drive_service, file_id)
                        if not file_bytes:
                            logging.error(f"[FORUM] Impossible de télécharger {name} ({cat})")
                            error_count += 1
                            continue
                    else:
                        logging.warning(f"[FORUM] Service Drive non fourni, skip {name}")
                        error_count += 1
                        continue

                    success = await self.post_card_to_forum(
                        cat, name, file_bytes, discoverer_name, discovery_index
                    )

                    if success:
                        posted_count += 1
                        logging.info(f"[FORUM] Carte postée avec succès: {name} ({cat})")
                    else:
                        error_count += 1

                    # Petite pause pour éviter le rate limiting
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logging.error(f"[FORUM] Erreur lors du post de {name}: {e}")
                    error_count += 1

            # Mettre à jour les messages de statut pour toutes les catégories
            logging.info("[FORUM] Mise à jour des messages de statut des catégories...")
            forum_channel = self.bot.get_channel(CARD_FORUM_CHANNEL_ID)
            if isinstance(forum_channel, discord.ForumChannel):
                for category in self.get_all_card_categories():
                    try:
                        thread = await self.get_or_create_category_thread(forum_channel, category)
                        if thread:
                            await self.update_category_status_message(thread, category, cards_by_category, upgrade_cards_by_category)
                            await asyncio.sleep(0.5)  # Éviter le rate limiting
                    except Exception as e:
                        logging.error(f"[FORUM] Erreur lors de la mise à jour du statut pour {category}: {e}")

            return posted_count, error_count

        except Exception as e:
            logging.error(f"[FORUM] Erreur lors de la population du forum: {e}")
            return 0, 0

    def _download_drive_file(self, drive_service, file_id: str) -> bytes:
        """
        Télécharge un fichier depuis Google Drive.

        Args:
            drive_service: Service Google Drive
            file_id: ID du fichier à télécharger

        Returns:
            bytes: Contenu du fichier ou None si erreur
        """
        try:
            request = drive_service.files().get_media(fileId=file_id)
            file_bytes = request.execute()
            return file_bytes
        except Exception as e:
            logging.error(f"[FORUM] Erreur lors du téléchargement du fichier {file_id}: {e}")
            return None

    async def clear_and_rebuild_category_thread(self, category: str, all_files: Dict[str, List[Dict]],
                                              drive_service=None, cards_by_category: dict = None,
                                              upgrade_cards_by_category: dict = None) -> Tuple[int, int]:
        """
        Vide complètement un thread de catégorie et le reconstruit avec toutes les cartes découvertes.

        Args:
            category: Nom de la catégorie à reconstruire
            all_files: Dictionnaire des fichiers par catégorie
            drive_service: Service Google Drive pour télécharger les images
            cards_by_category: Dictionnaire des cartes normales par catégorie
            upgrade_cards_by_category: Dictionnaire des cartes Full par catégorie

        Returns:
            Tuple[int, int]: (cartes_postées, erreurs)
        """
        try:
            forum_channel = self.bot.get_channel(CARD_FORUM_CHANNEL_ID)
            if not isinstance(forum_channel, discord.ForumChannel):
                logging.error(f"[FORUM] Canal {CARD_FORUM_CHANNEL_ID} n'est pas un ForumChannel")
                return 0, 1

            # Obtenir ou créer le thread de catégorie
            thread = await self.get_or_create_category_thread(forum_channel, category)
            if not thread:
                logging.error(f"[FORUM] Impossible d'obtenir le thread pour {category}")
                return 0, 1

            # Supprimer tous les messages du thread (sauf le premier message initial)
            try:
                messages_to_delete = []
                message_count = 0
                async for message in thread.history(limit=None):
                    message_count += 1
                    # Garder le premier message (message initial du thread)
                    if message.id != thread.id:
                        messages_to_delete.append(message)

                logging.info(f"[FORUM] Thread {category}: {message_count} messages totaux, {len(messages_to_delete)} à supprimer")

                if messages_to_delete:
                    # Supprimer les messages par lots pour éviter le rate limiting
                    for i in range(0, len(messages_to_delete), 10):
                        batch = messages_to_delete[i:i+10]
                        for message in batch:
                            try:
                                await message.delete()
                                await asyncio.sleep(0.2)  # Pause pour éviter le rate limiting
                            except discord.NotFound:
                                pass  # Message déjà supprimé
                            except Exception as e:
                                logging.warning(f"[FORUM] Erreur lors de la suppression du message {message.id}: {e}")

                    logging.info(f"[FORUM] Thread {category} vidé, {len(messages_to_delete)} messages supprimés")
                else:
                    logging.info(f"[FORUM] Thread {category} était déjà vide (sauf message initial)")

            except Exception as e:
                logging.error(f"[FORUM] Erreur lors du vidage du thread {category}: {e}")
                # Ne pas retourner d'erreur, continuer avec la reconstruction
                logging.info(f"[FORUM] Continuation de la reconstruction malgré l'erreur de vidage")

            # Reconstruire le thread avec les cartes de cette catégorie
            discoveries_cache = self.discovery_manager.storage.get_discoveries_cache()

            if not discoveries_cache or len(discoveries_cache) <= 1:
                return 0, 0

            # Filtrer et trier les découvertes pour cette catégorie
            discovery_rows = discoveries_cache[1:]  # Skip header
            category_discoveries = [row for row in discovery_rows if len(row) >= 6 and row[0] == category]
            category_discoveries.sort(key=lambda row: int(row[5]) if row[5].isdigit() else 0)

            logging.info(f"[FORUM] Reconstruction {category}: {len(category_discoveries)} découvertes trouvées")
            logging.info(f"[FORUM] Fichiers disponibles pour {category}: {len(all_files.get(category, []))}")

            posted_count = 0
            error_count = 0

            for row in category_discoveries:
                cat, name, discoverer_id_str, discoverer_name, timestamp, discovery_index = row
                discovery_index = int(discovery_index)

                logging.info(f"[FORUM] Traitement de la carte: {name} ({cat})")

                # Trouver le fichier de la carte
                file_id = next(
                    (f['id'] for f in all_files.get(cat, []) if f['name'].removesuffix(".png") == name),
                    None
                )
                if not file_id:
                    # Debug détaillé pour comprendre pourquoi le fichier n'est pas trouvé
                    available_files = [f['name'] for f in all_files.get(cat, [])]
                    logging.warning(f"[FORUM] Fichier non trouvé pour '{name}' dans {cat}")
                    logging.warning(f"[FORUM] Fichiers disponibles: {available_files[:10]}...")  # Limiter pour éviter les logs trop longs
                    error_count += 1
                    continue

                # Télécharger l'image et poster dans le forum
                try:
                    if drive_service:
                        logging.info(f"[FORUM] Téléchargement de {name} (ID: {file_id})")
                        file_bytes = self._download_drive_file(drive_service, file_id)
                        if not file_bytes:
                            logging.error(f"[FORUM] Impossible de télécharger {name} ({cat}) - fichier vide")
                            error_count += 1
                            continue
                        logging.info(f"[FORUM] Fichier téléchargé: {len(file_bytes)} bytes")
                    else:
                        logging.error(f"[FORUM] Service Drive non fourni pour {name}")
                        error_count += 1
                        continue

                    # Créer le fichier Discord avec un nom constant pour l'attachment
                    filename = "card.png"  # Nom constant pour l'URL attachment://

                    logging.info(f"[FORUM] Création du fichier Discord pour {name}")

                    # Créer le fichier Discord
                    file = discord.File(
                        fp=io.BytesIO(file_bytes),
                        filename=filename
                    )

                    # Créer l'embed avec l'URL d'attachment
                    embed = self.create_card_embed(name, cat, discoverer_name, discovery_index, f"attachment://{filename}")

                    # Poster l'embed avec l'image attachée directement
                    logging.info(f"[FORUM] Posting de l'embed avec image attachée pour {name} dans le thread {thread.name} (ID: {thread.id})")
                    sent_message = await thread.send(embed=embed, file=file)
                    posted_count += 1
                    logging.info(f"[FORUM] ✅ Carte repostée avec succès: {name} ({cat}) - Message ID: {sent_message.id}")

                    # Petite pause pour éviter le rate limiting
                    await asyncio.sleep(0.5)

                except discord.HTTPException as e:
                    logging.error(f"[FORUM] Erreur HTTP Discord lors du post de {name}: {e}")
                    error_count += 1
                except discord.Forbidden as e:
                    logging.error(f"[FORUM] Permissions insuffisantes pour poster {name}: {e}")
                    error_count += 1
                except Exception as e:
                    logging.error(f"[FORUM] Erreur générale lors du repost de {name}: {e}")
                    import traceback
                    logging.error(f"[FORUM] Traceback: {traceback.format_exc()}")
                    error_count += 1

            # Mettre à jour le message de statut pour cette catégorie
            try:
                await self.update_category_status_message(thread, category, cards_by_category, upgrade_cards_by_category)
                logging.info(f"[FORUM] Message de statut mis à jour pour {category}")
            except Exception as e:
                logging.error(f"[FORUM] Erreur lors de la mise à jour du statut pour {category}: {e}")

            logging.info(f"[FORUM] Reconstruction du thread {category} terminée: {posted_count} cartes postées, {error_count} erreurs")
            return posted_count, error_count

        except Exception as e:
            logging.error(f"[FORUM] Erreur lors de la reconstruction du thread {category}: {e}")
            return 0, 1

    async def diagnose_forum_state(self) -> Dict[str, any]:
        """
        Diagnostique l'état actuel du forum pour identifier les problèmes.

        Returns:
            Dict contenant les informations de diagnostic
        """
        try:
            forum_channel = self.bot.get_channel(CARD_FORUM_CHANNEL_ID)
            if not isinstance(forum_channel, discord.ForumChannel):
                return {"error": f"Canal {CARD_FORUM_CHANNEL_ID} n'est pas un ForumChannel"}

            diagnosis = {
                "forum_channel_id": CARD_FORUM_CHANNEL_ID,
                "active_threads": [],
                "archived_threads": [],
                "cache_threads": dict(self.category_threads),
                "expected_categories": self.get_all_card_categories(),
                "missing_categories": [],
                "duplicate_categories": []
            }

            # Analyser les threads actifs
            thread_names = []
            for thread in forum_channel.threads:
                diagnosis["active_threads"].append({
                    "name": thread.name,
                    "id": thread.id,
                    "message_count": thread.message_count,
                    "archived": thread.archived,
                    "locked": thread.locked
                })
                thread_names.append(thread.name)

            # Analyser TOUS les threads archivés (pas de limite)
            try:
                async for thread in forum_channel.archived_threads(limit=None):
                    diagnosis["archived_threads"].append({
                        "name": thread.name,
                        "id": thread.id,
                        "message_count": thread.message_count,
                        "archived": thread.archived,
                        "locked": thread.locked
                    })
                    thread_names.append(thread.name)
            except Exception as e:
                logging.warning(f"[FORUM] Erreur lors de la récupération des threads archivés: {e}")

            # Essayer aussi de récupérer via l'API différemment
            try:
                # Récupérer tous les threads du forum (actifs et archivés)
                all_threads = await forum_channel.fetch_archived_threads(limit=None)
                for thread in all_threads.threads:
                    if thread.name not in thread_names:  # Éviter les doublons
                        diagnosis["archived_threads"].append({
                            "name": thread.name,
                            "id": thread.id,
                            "message_count": getattr(thread, 'message_count', 0),
                            "archived": thread.archived,
                            "locked": getattr(thread, 'locked', False)
                        })
                        thread_names.append(thread.name)
            except Exception as e:
                logging.warning(f"[FORUM] Erreur lors de fetch_archived_threads: {e}")

            # Identifier les catégories manquantes et dupliquées
            expected_categories = set(diagnosis["expected_categories"])
            found_categories = set(thread_names)

            diagnosis["missing_categories"] = list(expected_categories - found_categories)

            # Chercher les doublons
            from collections import Counter
            category_counts = Counter(thread_names)
            diagnosis["duplicate_categories"] = [cat for cat, count in category_counts.items() if count > 1]

            return diagnosis

        except Exception as e:
            logging.error(f"[FORUM] Erreur lors du diagnostic: {e}")
            return {"error": str(e)}
