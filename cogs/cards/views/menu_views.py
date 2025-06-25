"""
Vues principales du menu des cartes.
"""

import discord
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...Cards import Cards


class CardsMenuView(discord.ui.View):
    """Vue principale du menu des cartes."""
    
    def __init__(self, cog: "Cards", user: discord.User):
        super().__init__(timeout=None)
        self.cog = cog
        self.user = user
        self.user_id = user.id
    
    @discord.ui.button(label="Tirer une carte", style=discord.ButtonStyle.primary)
    async def draw_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour tirer une carte."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)

        try:
            # Vérifier si l'utilisateur peut effectuer son tirage journalier
            if not self.cog.drawing_manager.can_perform_daily_draw(self.user.id):
                await interaction.followup.send(
                    "🚫 Vous avez déjà effectué votre tirage journalier aujourd'hui. Revenez demain !",
                    ephemeral=True
                )
                return

            # Effectuer le tirage journalier
            drawn_cards = await self.perform_draw(interaction)

            if not drawn_cards:
                await interaction.followup.send(
                    "❌ Une erreur est survenue lors du tirage.",
                    ephemeral=True
                )
                return

            # Créer l'embed de résultat
            embed = discord.Embed(
                title="🌅 Tirage journalier !",
                description="Vous avez reçu 3 cartes gratuites !",
                color=0xf1c40f
            )

            for i, (cat, name) in enumerate(drawn_cards, 1):
                display_name = name.removesuffix('.png')
                embed.add_field(
                    name=f"Carte {i}",
                    value=f"**{display_name}**\n*{cat}*",
                    inline=True
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

            # Annonce publique si nouvelles cartes
            await self.cog._handle_announce_and_wall(interaction, drawn_cards)
            
        except Exception as e:
            logging.error(f"[MENU] Erreur lors du tirage: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors du tirage.",
                ephemeral=True
            )
    
    async def perform_draw(self, interaction: discord.Interaction) -> list[tuple[str, str]]:
        """
        Effectue le tirage journalier de 3 cartes pour l'utilisateur.
        """
        # Vérifier si l'utilisateur peut effectuer son tirage journalier
        if not self.cog.drawing_manager.can_perform_daily_draw(self.user.id):
            return []  # Pas de tirage disponible

        # Effectuer le tirage journalier de 3 cartes
        drawn_cards = self.cog.drawing_manager.draw_cards(3)

        # Ajouter les cartes à l'inventaire
        for cat, name in drawn_cards:
            self.cog.add_card_to_user(self.user.id, cat, name)

        # Enregistrer le tirage journalier
        self.cog.drawing_manager.record_daily_draw(self.user.id)

        return drawn_cards
    
    @discord.ui.button(label="Ma galerie", style=discord.ButtonStyle.secondary)
    async def view_gallery(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour voir la galerie de cartes."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Utiliser la méthode originale du cog
            result = self.cog.generate_paginated_gallery_embeds(self.user, 0)

            if not result:
                await interaction.followup.send(
                    "❌ Vous n'avez aucune carte dans votre collection.",
                    ephemeral=True
                )
                return

            embed_normales, embed_full, pagination_info = result
            embeds = [embed_normales, embed_full] if embed_full else [embed_normales]

            # Importer ici pour éviter les imports circulaires
            from .gallery_views import PaginatedGalleryView

            # Créer la vue de galerie paginée
            gallery_view = PaginatedGalleryView(self.cog, self.user)
            await interaction.followup.send(embeds=embeds, view=gallery_view, ephemeral=True)
            
        except Exception as e:
            logging.error(f"[MENU] Erreur lors de l'affichage de la galerie: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de l'affichage de la galerie.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Échanges", style=discord.ButtonStyle.secondary)
    async def trading_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour accéder au menu des échanges."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Importer ici pour éviter les imports circulaires
            from .trade_views import TradeMenuView
            
            # Créer la vue de trading
            trade_view = TradeMenuView(self.cog, self.user)
            
            embed = discord.Embed(
                title="🔄 Menu des échanges",
                description="Choisissez une action d'échange :",
                color=0x3498db
            )
            
            await interaction.followup.send(embed=embed, view=trade_view, ephemeral=True)
            
        except Exception as e:
            logging.error(f"[MENU] Erreur lors de l'affichage du menu d'échange: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de l'affichage du menu d'échange.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Tirage sacrificiel", style=discord.ButtonStyle.danger)
    async def sacrificial_draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour le tirage sacrificiel."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Récupérer les cartes éligibles (non-Full)
            user_cards = self.cog.get_user_cards(self.user.id)
            eligible_cards = [(cat, name) for cat, name in user_cards if not "(Full)" in name]
            
            if len(eligible_cards) < 5:
                await interaction.followup.send(
                    f"❌ Vous devez avoir au moins 5 cartes (non-Full) pour effectuer un tirage sacrificiel. "
                    f"Vous en avez {len(eligible_cards)}.",
                    ephemeral=True
                )
                return
            
            # Sélectionner les cartes sacrificielles du jour
            selected_cards = self.cog.drawing_manager.select_daily_sacrificial_cards(
                self.user.id, eligible_cards
            )
            
            if not selected_cards:
                await interaction.followup.send(
                    "❌ Aucune carte disponible pour le tirage sacrificiel aujourd'hui.",
                    ephemeral=True
                )
                return
            
            # Importer ici pour éviter les imports circulaires
            from .menu_views import SacrificialDrawConfirmationView
            
            # Créer la vue de confirmation
            confirmation_view = SacrificialDrawConfirmationView(self.cog, self.user, selected_cards)
            
            # Créer l'embed de confirmation
            embed = discord.Embed(
                title="⚔️ Tirage sacrificiel",
                description="Cartes sélectionnées pour le sacrifice d'aujourd'hui :",
                color=0xe74c3c
            )
            
            for i, (cat, name) in enumerate(selected_cards, 1):
                display_name = name.removesuffix('.png')
                user_count = user_cards.count((cat, name))
                embed.add_field(
                    name=f"Carte {i}",
                    value=f"**{display_name}** ({cat})\n*Vous en possédez: {user_count}*",
                    inline=True
                )
            
            embed.add_field(
                name="⚠️ Attention",
                value="Ces cartes seront **définitivement perdues** en échange d'une carte rare !",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, view=confirmation_view, ephemeral=True)
            
        except Exception as e:
            logging.error(f"[MENU] Erreur lors du tirage sacrificiel: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors du tirage sacrificiel.",
                ephemeral=True
            )

    @discord.ui.button(label="🏆 Classement", style=discord.ButtonStyle.secondary)
    async def show_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour afficher le classement."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            leaderboard = self.cog.get_leaderboard()

            # Get the excluding full counts for ALL users, not just top 5
            all_excluding_full_counts = self.cog.get_unique_card_counts_excluding_full()

            embed = discord.Embed(title="🏆 Top 5 des collectionneurs", color=0x4E5D94)
            for idx, (uid, count) in enumerate(leaderboard, start=1):
                user = self.cog.bot.get_user(uid)
                name = user.display_name if user else str(uid)
                excluding_full_count = all_excluding_full_counts.get(uid, 0)
                embed.add_field(
                    name=f"#{idx} {name}",
                    value=f"{count} cartes différentes | Hors Full : {excluding_full_count}",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f"[LEADERBOARD] Erreur lors de l'affichage du classement: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de l'affichage du classement.",
                ephemeral=True
            )


class SacrificialDrawConfirmationView(discord.ui.View):
    """Vue de confirmation pour le tirage sacrificiel."""
    
    def __init__(self, cog: "Cards", user: discord.User, selected_cards: list[tuple[str, str]]):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user
        self.selected_cards = selected_cards
    
    @discord.ui.button(label="Confirmer le sacrifice", style=discord.ButtonStyle.danger)
    async def confirm_sacrifice(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirme et effectue le tirage sacrificiel."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Vérifier que l'utilisateur possède encore toutes les cartes
            user_cards = self.cog.get_user_cards(self.user.id)
            for cat, name in self.selected_cards:
                if (cat, name) not in user_cards:
                    await interaction.followup.send(
                        f"❌ Vous ne possédez plus la carte **{name.removesuffix('.png')}** ({cat}).",
                        ephemeral=True
                    )
                    return
            
            # Retirer les cartes sacrifiées
            for cat, name in self.selected_cards:
                if not self.cog.remove_card_from_user(self.user.id, cat, name):
                    await interaction.followup.send(
                        "❌ Erreur lors du retrait des cartes sacrifiées.",
                        ephemeral=True
                    )
                    return
            
            # Effectuer le tirage rare (catégories rares uniquement)
            rare_categories = ["Secrète", "Fondateur", "Historique", "Maître", "Black Hole"]
            drawn_cards = []
            
            for _ in range(1):  # Un seul tirage rare
                category = self.cog.drawing_manager.random.choice(rare_categories)
                available_cards = self.cog.cards_by_category.get(category, [])
                if available_cards:
                    selected_card = self.cog.drawing_manager.random.choice(available_cards)
                    card_name = selected_card['name'].removesuffix('.png')
                    drawn_cards.append((category, card_name))
                    self.cog.add_card_to_user(self.user.id, category, card_name)
            
            if drawn_cards:
                cat, name = drawn_cards[0]
                embed = discord.Embed(
                    title="⚔️ Sacrifice accompli !",
                    description=f"Vous avez obtenu : **{name}** ({cat})",
                    color=0x27ae60
                )
                
                # Annonce publique
                await self.cog._handle_announce_and_wall(interaction, drawn_cards)
            else:
                embed = discord.Embed(
                    title="❌ Erreur",
                    description="Aucune carte rare disponible.",
                    color=0xe74c3c
                )
            
            # Désactiver tous les boutons
            for child in self.children:
                child.disabled = True
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"[SACRIFICIAL] Erreur lors du sacrifice: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors du sacrifice.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_sacrifice(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Annule le tirage sacrificiel."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        # Désactiver tous les boutons
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(
            content="❌ Tirage sacrificiel annulé.",
            embed=None,
            view=self
        )
