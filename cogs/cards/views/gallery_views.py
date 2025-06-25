"""
Vues pour l'affichage des galeries de cartes.
"""

import discord
import logging
from typing import TYPE_CHECKING, Optional, Tuple, List
import math

if TYPE_CHECKING:
    from ...Cards import Cards


class PaginatedGalleryView(discord.ui.View):
    """Vue de galerie paginée pour les cartes."""
    
    def __init__(self, cog: "Cards", user: discord.User, current_page: int = 0):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.cog = cog
        self.user = user
        self.current_page = current_page
        self.cards_per_page = 15
        
        # Mettre à jour l'état des boutons
        self._update_buttons()
    
    def _update_buttons(self):
        """Met à jour l'état des boutons de navigation."""
        # Récupérer les cartes pour calculer le nombre de pages
        user_cards = self.cog.get_user_cards(self.user.id)
        if not user_cards:
            return
        
        # Séparer les cartes normales et Full
        normal_cards = [(cat, name) for cat, name in user_cards if not "(Full)" in name]
        full_cards = [(cat, name) for cat, name in user_cards if "(Full)" in name]
        
        # Calculer le nombre de pages basé sur les cartes normales
        unique_normal = list(set(normal_cards))
        total_pages = max(1, math.ceil(len(unique_normal) / self.cards_per_page))
        
        # Mettre à jour les boutons
        self.previous_page.disabled = self.current_page <= 0
        self.next_page.disabled = self.current_page >= total_pages - 1
    
    async def get_gallery_page(self, page: int) -> Optional[Tuple[discord.Embed, Optional[discord.Embed], dict]]:
        """
        Récupère une page de la galerie.
        
        Returns:
            Tuple: (embed_normales, embed_full, pagination_info) ou None
        """
        try:
            user_cards = self.cog.get_user_cards(self.user.id)
            if not user_cards:
                return None
            
            # Séparer les cartes normales et Full
            normal_cards = [(cat, name) for cat, name in user_cards if not "(Full)" in name]
            full_cards = [(cat, name) for cat, name in user_cards if "(Full)" in name]
            
            # Trier les cartes normales par rareté puis alphabétiquement
            sorted_normal = self._sort_cards_by_rarity(normal_cards)
            unique_normal = []
            seen = set()
            for cat, name in sorted_normal:
                if (cat, name) not in seen:
                    unique_normal.append((cat, name))
                    seen.add((cat, name))
            
            # Pagination des cartes normales
            start_idx = page * self.cards_per_page
            end_idx = start_idx + self.cards_per_page
            page_cards = unique_normal[start_idx:end_idx]
            
            # Créer l'embed des cartes normales
            embed_normales = discord.Embed(
                title=f"🎴 Galerie de {self.user.display_name}",
                color=0x3498db
            )
            
            if page_cards:
                # Grouper par catégorie
                by_category = {}
                for cat, name in page_cards:
                    if cat not in by_category:
                        by_category[cat] = []
                    count = user_cards.count((cat, name))
                    display_name = name.removesuffix('.png')
                    
                    # Ajouter l'ID de carte si disponible
                    card_id = self.cog.get_card_id(cat, name)
                    if card_id:
                        display_name += f" ({card_id})"
                    
                    by_category[cat].append(f"• {display_name} (x{count})")
                
                # Ajouter les champs par catégorie
                for cat in self.cog.get_all_card_categories():
                    if cat in by_category and cat != "Full":
                        embed_normales.add_field(
                            name=f"📂 {cat}",
                            value="\n".join(by_category[cat]),
                            inline=True
                        )
            else:
                embed_normales.add_field(
                    name="Aucune carte",
                    value="Vous n'avez aucune carte dans votre collection.",
                    inline=False
                )
            
            # Informations de pagination
            total_pages = max(1, math.ceil(len(unique_normal) / self.cards_per_page))
            embed_normales.set_footer(text=f"Page {page + 1}/{total_pages} • {len(unique_normal)} cartes uniques")
            
            # Créer l'embed des cartes Full si nécessaire
            embed_full = None
            if full_cards:
                unique_full = list(set(full_cards))
                sorted_full = self._sort_cards_by_rarity(unique_full)
                
                embed_full = discord.Embed(
                    title="✨ Cartes Full",
                    color=0xf1c40f
                )
                
                # Grouper par catégorie
                by_category_full = {}
                for cat, name in sorted_full:
                    if cat not in by_category_full:
                        by_category_full[cat] = []
                    count = user_cards.count((cat, name))
                    display_name = name.removesuffix('.png')
                    
                    # Ajouter l'ID de carte si disponible
                    card_id = self.cog.get_card_id(cat, name)
                    if card_id:
                        display_name += f" ({card_id})"
                    
                    by_category_full[cat].append(f"• {display_name} (x{count})")
                
                # Ajouter les champs par catégorie
                for cat in self.cog.get_all_card_categories():
                    if cat in by_category_full and cat != "Full":
                        embed_full.add_field(
                            name=f"📂 {cat}",
                            value="\n".join(by_category_full[cat]),
                            inline=True
                        )
                
                embed_full.set_footer(text=f"{len(unique_full)} cartes Full uniques")
            
            pagination_info = {
                'current_page': page,
                'total_pages': total_pages,
                'total_cards': len(unique_normal)
            }
            
            return embed_normales, embed_full, pagination_info
            
        except Exception as e:
            logging.error(f"[GALLERY] Erreur lors de la création de la page: {e}")
            return None
    
    def _sort_cards_by_rarity(self, cards: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Trie les cartes par rareté puis alphabétiquement."""
        category_order = {cat: i for i, cat in enumerate(self.cog.get_all_card_categories())}
        
        return sorted(cards, key=lambda x: (
            category_order.get(x[0], 999),  # Ordre de rareté
            x[1].lower()  # Ordre alphabétique
        ))
    
    @discord.ui.button(label="◀️ Précédent", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour la page précédente."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        if self.current_page > 0:
            self.current_page -= 1
            await self._update_gallery(interaction)
    
    @discord.ui.button(label="▶️ Suivant", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour la page suivante."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        # Vérifier qu'il y a une page suivante
        user_cards = self.cog.get_user_cards(self.user.id)
        normal_cards = [(cat, name) for cat, name in user_cards if not "(Full)" in name]
        unique_normal = list(set(normal_cards))
        total_pages = max(1, math.ceil(len(unique_normal) / self.cards_per_page))
        
        if self.current_page < total_pages - 1:
            self.current_page += 1
            await self._update_gallery(interaction)
    
    async def _update_gallery(self, interaction: discord.Interaction):
        """Met à jour l'affichage de la galerie."""
        await interaction.response.defer()
        
        try:
            result = await self.get_gallery_page(self.current_page)
            if not result:
                await interaction.followup.send(
                    "❌ Erreur lors de la mise à jour de la galerie.",
                    ephemeral=True
                )
                return
            
            embed_normales, embed_full, pagination_info = result
            embeds = [embed_normales, embed_full] if embed_full else [embed_normales]
            
            # Mettre à jour les boutons
            self._update_buttons()
            
            await interaction.edit_original_response(embeds=embeds, view=self)
            
        except Exception as e:
            logging.error(f"[GALLERY] Erreur lors de la mise à jour: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de la mise à jour.",
                ephemeral=True
            )
    
    @discord.ui.button(label="🔍 Afficher une carte", style=discord.ButtonStyle.primary)
    async def show_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour afficher une carte spécifique."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        # Importer ici pour éviter les imports circulaires
        from .modal_views import CardNameModal
        
        modal = CardNameModal(self.cog, self.user)
        await interaction.response.send_modal(modal)


class AdminPaginatedGalleryView(discord.ui.View):
    """Vue de galerie paginée pour les commandes admin (non-ephemeral)."""
    
    def __init__(self, cog: "Cards", user: discord.User, current_page: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.current_page = current_page
        self.cards_per_page = 15
        
        # Mettre à jour l'état des boutons
        self._update_buttons()
    
    def _update_buttons(self):
        """Met à jour l'état des boutons de navigation."""
        # Récupérer les cartes pour calculer le nombre de pages
        user_cards = self.cog.get_user_cards(self.user.id)
        if not user_cards:
            return
        
        # Séparer les cartes normales et Full
        normal_cards = [(cat, name) for cat, name in user_cards if not "(Full)" in name]
        
        # Calculer le nombre de pages basé sur les cartes normales
        unique_normal = list(set(normal_cards))
        total_pages = max(1, math.ceil(len(unique_normal) / self.cards_per_page))
        
        # Mettre à jour les boutons
        self.previous_page.disabled = self.current_page <= 0
        self.next_page.disabled = self.current_page >= total_pages - 1
    
    @discord.ui.button(label="◀️ Précédent", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour la page précédente."""
        if self.current_page > 0:
            self.current_page -= 1
            await self._update_gallery(interaction)
    
    @discord.ui.button(label="▶️ Suivant", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour la page suivante."""
        # Vérifier qu'il y a une page suivante
        user_cards = self.cog.get_user_cards(self.user.id)
        normal_cards = [(cat, name) for cat, name in user_cards if not "(Full)" in name]
        unique_normal = list(set(normal_cards))
        total_pages = max(1, math.ceil(len(unique_normal) / self.cards_per_page))
        
        if self.current_page < total_pages - 1:
            self.current_page += 1
            await self._update_gallery(interaction)
    
    async def _update_gallery(self, interaction: discord.Interaction):
        """Met à jour l'affichage de la galerie."""
        await interaction.response.defer()
        
        try:
            # Utiliser la même logique que PaginatedGalleryView
            gallery_view = PaginatedGalleryView(self.cog, self.user, self.current_page)
            result = await gallery_view.get_gallery_page(self.current_page)
            
            if not result:
                await interaction.followup.send(
                    "❌ Erreur lors de la mise à jour de la galerie."
                )
                return
            
            embed_normales, embed_full, pagination_info = result
            embeds = [embed_normales, embed_full] if embed_full else [embed_normales]
            
            # Mettre à jour les boutons
            self._update_buttons()
            
            await interaction.edit_original_response(embeds=embeds, view=self)
            
        except Exception as e:
            logging.error(f"[ADMIN_GALLERY] Erreur lors de la mise à jour: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de la mise à jour."
            )


class GalleryActionView(discord.ui.View):
    """Vue d'actions pour la galerie."""
    
    def __init__(self, cog: "Cards", user: discord.User):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user
    
    @discord.ui.button(label="🔍 Afficher une carte", style=discord.ButtonStyle.primary)
    async def show_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour afficher une carte spécifique."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        # Importer ici pour éviter les imports circulaires
        from .modal_views import CardNameModal
        
        modal = CardNameModal(self.cog, self.user)
        await interaction.response.send_modal(modal)
