"""
Gestion du forum des cartes.
Gère la création de threads, le posting des cartes découvertes, etc.
"""

import asyncio
import logging
import discord
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
    
    def get_all_card_categories(self) -> List[str]:
        """Retourne la liste complète des catégories de cartes, incluant 'Full'."""
        categories = ALL_CATEGORIES.copy()
        categories.append("Full")  # Ajouter la catégorie Full
        return categories
    
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
                    thread = await forum_channel.fetch_thread(thread_id)
                    if thread and not thread.archived:
                        return thread
                except discord.NotFound:
                    # Thread supprimé, retirer du cache
                    del self.category_threads[category]
            
            # Chercher le thread existant
            async for thread in forum_channel.archived_threads(limit=None):
                if thread.name == category:
                    self.category_threads[category] = thread.id
                    if thread.archived:
                        await thread.edit(archived=False)
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
            thread = await self.get_or_create_category_thread(forum_channel, category)
            if not thread:
                return False
            
            # Créer le message de découverte
            display_name = name.removesuffix('.png')
            message = f"**{display_name}** (#{discovery_index})\n"
            message += f"Découvert par: {discoverer_name}"
            
            # Créer le fichier Discord
            file = discord.File(
                fp=discord.utils._BytesIOProxy(file_bytes),
                filename=f"{name}.png" if not name.endswith('.png') else name
            )
            
            # Poster dans le thread
            await thread.send(content=message, file=file)
            logging.info(f"[FORUM] Carte postée: {name} ({category}) par {discoverer_name}")
            return True
            
        except Exception as e:
            logging.error(f"[FORUM] Erreur lors du post de la carte {name}: {e}")
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
    
    async def populate_forum_threads(self, all_files: Dict[str, List[Dict]]) -> Tuple[int, int]:
        """
        Peuple les threads du forum avec toutes les cartes découvertes.
        
        Args:
            all_files: Dictionnaire des fichiers par catégorie
        
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
                    error_count += 1
                    continue
                
                # Télécharger l'image et poster dans le forum
                try:
                    # Note: Cette méthode nécessitera l'accès au service Google Drive
                    # qui sera fourni lors de l'intégration complète
                    file_bytes = b''  # Placeholder
                    success = await self.post_card_to_forum(
                        cat, name, file_bytes, discoverer_name, discovery_index
                    )
                    
                    if success:
                        posted_count += 1
                    else:
                        error_count += 1
                    
                    # Petite pause pour éviter le rate limiting
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logging.error(f"[FORUM] Erreur lors du post de {name}: {e}")
                    error_count += 1
            
            return posted_count, error_count
            
        except Exception as e:
            logging.error(f"[FORUM] Erreur lors de la population du forum: {e}")
            return 0, 0
