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
    
    @discord.ui.button(label="🌅 Tirage journalier", style=discord.ButtonStyle.primary)
    async def daily_draw(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        Effectue le tirage journalier de 3 cartes pour l'utilisateur avec affichage original.
        """
        # Vérifier si l'utilisateur peut effectuer son tirage journalier
        if not self.cog.drawing_manager.can_perform_daily_draw(self.user.id):
            return []  # Pas de tirage disponible

        # Effectuer le tirage journalier de 3 cartes
        drawn_cards = self.cog.drawing_manager.draw_cards(3)

        # Annonce publique si nouvelles cartes
        discovered_cards = self.cog.discovery_manager.get_discovered_cards()
        new_cards = [c for c in drawn_cards if c not in discovered_cards]
        if new_cards:
            await self.cog._handle_announce_and_wall(interaction, new_cards)

        # Affichage des cartes avec embeds/images (style original)
        embed_msgs = []
        for cat, name in drawn_cards:
            # Recherche du fichier image (inclut cartes Full)
            file_id = next(
                (f["id"] for f in (self.cog.cards_by_category.get(cat, []) + self.cog.upgrade_cards_by_category.get(cat, []))
                if f["name"].removesuffix(".png") == name),
                None,
            )
            if file_id:
                file_bytes = self.cog.download_drive_file(file_id)
                embed, image_file = self.cog.build_card_embed(cat, name, file_bytes)
                embed_msgs.append((embed, image_file))

        if embed_msgs:
            first_embed, first_file = embed_msgs[0]
            await interaction.edit_original_response(content=None, embed=first_embed, attachments=[first_file])
            for em, f in embed_msgs[1:]:
                await interaction.followup.send(embed=em, file=f, ephemeral=False)

        # Ajouter les cartes à l'inventaire
        for cat, name in drawn_cards:
            self.cog.add_card_to_user(self.user.id, cat, name)

        # Maintenant que l'inventaire est à jour, on gère les upgrades
        await self.cog.check_for_upgrades(interaction, self.user.id, drawn_cards)

        # Enregistrer le tirage journalier
        self.cog.drawing_manager.record_daily_draw(self.user.id)

        return drawn_cards

    @discord.ui.button(label="⚔️ Tirage sacrificiel", style=discord.ButtonStyle.danger)
    async def sacrificial_draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour le tirage sacrificiel."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Vérifier si l'utilisateur peut effectuer son tirage sacrificiel
            if not self.cog.drawing_manager.can_perform_sacrificial_draw(interaction.user.id):
                await interaction.followup.send(
                    "🚫 Vous avez déjà effectué votre tirage sacrificiel aujourd'hui. Revenez demain !",
                    ephemeral=True
                )
                return

            # Récupérer les cartes éligibles (non-Full) avec cache optimisé
            user_cards = self.cog.get_user_cards(interaction.user.id)
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
                interaction.user.id, eligible_cards
            )

            if not selected_cards:
                await interaction.followup.send(
                    "❌ Aucune carte disponible pour le tirage sacrificiel aujourd'hui.",
                    ephemeral=True
                )
                return

            # Créer la vue de confirmation
            confirmation_view = SacrificialDrawConfirmationView(self.cog, interaction.user, selected_cards)

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
                value="Ces cartes seront **définitivement perdues** en échange d'une carte rare avec chance de Full !",
                inline=False
            )

            await interaction.followup.send(embed=embed, view=confirmation_view, ephemeral=True)

        except Exception as e:
            logging.error(f"[SACRIFICIAL_DRAW] Erreur: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors du tirage sacrificiel.",
                ephemeral=True
            )

    @discord.ui.button(label="📚 Ma galerie", style=discord.ButtonStyle.secondary)
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
            embeds = [embed_normales]
            if embed_full:
                embeds.append(embed_full)

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
    
# Ancien bouton tirage sacrificiel supprimé - maintenant placé après le tirage journalier

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

            # Utiliser les opérations batch optimisées pour retirer les cartes
            if not self.cog.batch_remove_cards_from_user(self.user.id, self.selected_cards):
                await interaction.followup.send(
                    "❌ Erreur lors du retrait des cartes sacrifiées.",
                    ephemeral=True
                )
                return

            # Effectuer le tirage rare avec attribution des Full cards
            drawn_cards = self.cog.drawing_manager.draw_cards(1, rare_only=True)

            if drawn_cards:
                # Ajouter la carte tirée à l'inventaire
                cat, name = drawn_cards[0]
                self.cog.add_card_to_user(self.user.id, cat, name)

                # Enregistrer le tirage sacrificiel
                self.cog.drawing_manager.record_sacrificial_draw(self.user.id)
            
            if drawn_cards:
                cat, name = drawn_cards[0]
                display_name = name.removesuffix('.png')
                is_full = "(Full)" in name

                embed = discord.Embed(
                    title="⚔️ Sacrifice accompli !",
                    description=f"Vous avez obtenu : **{display_name}** ({cat})",
                    color=0x27ae60
                )

                if is_full:
                    embed.add_field(
                        name="✨ Variante Full !",
                        value="Félicitations ! Vous avez obtenu une variante Full rare !",
                        inline=False
                    )

                # Affichage des cartes avec embeds/images (style original)
                embed_msgs = []
                for cat, name in drawn_cards:
                    # Recherche du fichier image (inclut cartes Full)
                    file_id = next(
                        (f["id"] for f in (self.cog.cards_by_category.get(cat, []) + self.cog.upgrade_cards_by_category.get(cat, []))
                        if f["name"].removesuffix(".png") == name),
                        None,
                    )
                    if file_id:
                        file_bytes = self.cog.download_drive_file(file_id)
                        embed, image_file = self.cog.build_card_embed(cat, name, file_bytes)
                        embed_msgs.append((embed, image_file))

                if embed_msgs:
                    for embed, image_file in embed_msgs:
                        await interaction.followup.send(embed=embed, file=image_file, ephemeral=False)

                # Annonce publique et mur des cartes
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
