"""
Vues pour l'affichage des galeries de cartes.
"""

import discord
import logging
from typing import TYPE_CHECKING, Optional, Tuple, List
import math

if TYPE_CHECKING:
    from ...Cards import Cards


class GalleryView(discord.ui.View):
    """Vue de galerie complète pour les cartes."""

    def __init__(self, cog: "Cards", user: discord.User):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.cog = cog
        self.user = user

    async def get_gallery_embeds(self) -> Optional[List[discord.Embed]]:
        """
        Récupère la galerie complète.

        Returns:
            List[discord.Embed]: Liste des embeds de la galerie ou None
        """
        try:
            # Utiliser la méthode de galerie complète du cog
            result = self.cog.generate_gallery_embeds(self.user)
            if result is None:
                logging.warning(f"[GALLERY] Aucune carte trouvée pour l'utilisateur {self.user.id}")
            return result

        except Exception as e:
            logging.error(f"[GALLERY] Erreur lors de la création de la galerie: {e}")
            return None



    @discord.ui.button(label="🔍 Voir carte", style=discord.ButtonStyle.primary)
    async def show_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour afficher une carte spécifique avec ses informations."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        # Importer ici pour éviter les imports circulaires
        from .modal_views import CardNameModal

        modal = CardNameModal(self.cog, self.user)
        await interaction.response.send_modal(modal)


class AdminGalleryView(discord.ui.View):
    """Vue de galerie complète pour les commandes admin (non-ephemeral)."""

    def __init__(self, cog: "Cards", user: discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user




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
