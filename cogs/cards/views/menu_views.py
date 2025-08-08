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

        # Vérifier s'il y a des bonus non réclamés et ajouter le bouton si nécessaire
        unclaimed_bonus_count = self.cog.get_user_unclaimed_bonus_count(user.id)
        if unclaimed_bonus_count > 0:
            self.add_bonus_draw_button(unclaimed_bonus_count)

    def add_bonus_draw_button(self, bonus_count: int):
        """Ajoute le bouton de tirage bonus en rouge."""
        bonus_button = discord.ui.Button(
            label=f"🎁 Tirage bonus ({bonus_count})",
            style=discord.ButtonStyle.danger,  # Rouge pour la visibilité
            custom_id="bonus_draw",
            row=3  # Placer le bouton bonus sur la quatrième ligne
        )
        bonus_button.callback = self.bonus_draw_callback
        self.add_item(bonus_button)

    async def bonus_draw_callback(self, interaction: discord.Interaction):
        """Callback pour le bouton de tirage bonus."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        # Vérifier que le tirage se fait dans le bon salon
        if interaction.channel_id != 1361993326215172218:
            await interaction.response.send_message(
                "🚫 Les tirages ne sont autorisés que dans le salon <#1361993326215172218>.",
                ephemeral=True
            )
            return

        # Répondre immédiatement avec un message éphémère
        await interaction.response.send_message(
            "🎁 **Tirage bonus en cours...**",
            ephemeral=True
        )

        try:
            # Vérifier si l'utilisateur a des bonus disponibles
            bonus_count = self.cog.get_user_unclaimed_bonus_count(self.user.id)
            if bonus_count <= 0:
                await interaction.followup.send(
                    "🚫 Vous n'avez aucun tirage bonus disponible.",
                    ephemeral=True
                )
                return

            # Effectuer le tirage bonus (qui gère déjà l'affichage)
            drawn_cards = await self.perform_bonus_draw(interaction)

            if not drawn_cards:
                await interaction.followup.send(
                    "❌ Une erreur est survenue lors du tirage bonus.",
                    ephemeral=True
                )
                return

            # L'affichage est déjà géré dans perform_bonus_draw() avec les images des cartes

        except Exception as e:
            logging.error(f"[MENU] Erreur lors du tirage bonus: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors du tirage bonus.",
                ephemeral=True
            )
    
    @discord.ui.button(label="🌅 Tirage journalier", style=discord.ButtonStyle.primary, row=0)
    async def daily_draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour tirer une carte."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        # Vérifier que le tirage se fait dans le bon salon
        if interaction.channel_id != 1361993326215172218:
            await interaction.response.send_message(
                "🚫 Les tirages ne sont autorisés que dans le salon <#1361993326215172218>.",
                ephemeral=True
            )
            return

        # Répondre immédiatement avec un message éphémère
        await interaction.response.send_message(
            "🌅 **Tirage journalier en cours...**",
            ephemeral=True
        )

        try:
            # Vérifier si l'utilisateur peut effectuer son tirage journalier
            if not self.cog.drawing_manager.can_perform_daily_draw(self.user.id):
                await interaction.followup.send(
                    "🚫 Vous avez déjà effectué votre tirage journalier aujourd'hui. Revenez demain !",
                    ephemeral=True
                )
                return

            # Effectuer le tirage journalier (qui gère déjà l'affichage)
            drawn_cards = await self.perform_draw(interaction)

            if not drawn_cards:
                await interaction.followup.send(
                    "❌ Une erreur est survenue lors du tirage.",
                    ephemeral=True
                )
                return

            # L'affichage est déjà géré dans perform_draw() avec les images des cartes

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
        # NOTE: La vérification can_perform_daily_draw() a déjà été faite dans le bouton
        # Ne pas la refaire ici pour éviter les problèmes de cache

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
                if file_bytes:
                    embed, image_file = self.cog.build_card_embed(cat, name, file_bytes, self.user)
                    embed_msgs.append((embed, image_file))

        if embed_msgs:
            # Envoyer toutes les cartes directement dans le salon comme messages indépendants
            for embed, file in embed_msgs:
                await interaction.channel.send(embed=embed, file=file)

        # ——————————— COMMIT ———————————
        # 1) Ajouter les cartes à l'inventaire
        for cat, name in drawn_cards:
            self.cog.add_card_to_user(self.user.id, cat, name,
                                    user_name=self.user.display_name,
                                    source="tirage_journalier")

        # 2) Logger le tirage journalier
        if self.cog.storage.logging_manager:
            logging.info(f"[DAILY_DRAW] Tentative de logging pour {self.user.display_name} ({self.user.id})")
            logging.info(f"[DAILY_DRAW] Cartes tirées: {drawn_cards}")

            success = self.cog.storage.logging_manager.log_card_draw(
                user_id=self.user.id,
                user_name=self.user.display_name,
                cards=drawn_cards,
                draw_type="DAILY",
                source="tirage_journalier"
            )

            if success:
                logging.info(f"[DAILY_DRAW] ✅ Logging réussi pour {self.user.display_name}")
            else:
                logging.error(f"[DAILY_DRAW] ❌ Échec du logging pour {self.user.display_name}")
        else:
            logging.error(f"[DAILY_DRAW] ❌ Logging manager non disponible pour {self.user.display_name}")

        # 3) Enregistrer le tirage journalier (ceci invalide le cache et marque l'utilisateur pour vérification)
        self.cog.drawing_manager.record_daily_draw(self.user.id)

        # 4) Traiter toutes les vérifications d'upgrade en attente
        await self.cog.process_all_pending_upgrade_checks(interaction, 1361993326215172218)

        return drawn_cards

    async def perform_bonus_draw(self, interaction: discord.Interaction) -> list[tuple[str, str]]:
        """
        Effectue un tirage bonus de 3 cartes pour l'utilisateur avec affichage original.
        Utilise un seul bonus à la fois.
        """
        # Effectuer le tirage bonus de 3 cartes (même logique que le tirage journalier)
        drawn_cards = self.cog.drawing_manager.draw_cards(3)

        # Annonce publique si nouvelles cartes
        discovered_cards = self.cog.discovery_manager.get_discovered_cards()
        new_cards = [c for c in drawn_cards if c not in discovered_cards]
        if new_cards:
            await self.cog._handle_announce_and_wall(interaction, new_cards)

        # Affichage des cartes avec embeds/images (même logique que daily_draw_callback)
        embed_msgs = []
        for cat, name in drawn_cards:
            try:
                # Recherche du fichier image (inclut cartes Full)
                file_id = next(
                    (f["id"] for f in (self.cog.cards_by_category.get(cat, []) + self.cog.upgrade_cards_by_category.get(cat, []))
                    if f["name"].removesuffix(".png") == name),
                    None,
                )
                if file_id:
                    file_bytes = self.cog.download_drive_file(file_id)
                    if file_bytes:
                        embed, image_file = self.cog.build_card_embed(cat, name, file_bytes, self.user)
                        embed_msgs.append((embed, image_file))
                    else:
                        logging.warning(f"[BONUS_DRAW] Impossible de télécharger l'image pour {name} ({cat})")
                else:
                    logging.warning(f"[BONUS_DRAW] Image non trouvée pour {name} ({cat})")
            except Exception as e:
                logging.error(f"[BONUS_DRAW] Erreur lors de l'affichage de {name}: {e}")

        if embed_msgs:
            # Envoyer toutes les cartes directement dans le salon comme messages indépendants
            for embed, file in embed_msgs:
                await interaction.channel.send(embed=embed, file=file)

        # ——————————— COMMIT ———————————
        # 1) Ajouter les cartes à l'inventaire
        for cat, name in drawn_cards:
            self.cog.add_card_to_user(self.user.id, cat, name,
                                    user_name=self.user.display_name,
                                    source="tirage_bonus")

        # 2) Logger le tirage bonus
        if self.cog.storage.logging_manager:
            logging.info(f"[BONUS_DRAW] Tentative de logging pour {self.user.display_name} ({self.user.id})")
            logging.info(f"[BONUS_DRAW] Cartes tirées: {drawn_cards}")

            success = self.cog.storage.logging_manager.log_card_draw(
                user_id=self.user.id,
                user_name=self.user.display_name,
                cards=drawn_cards,
                draw_type="BONUS",
                source="tirage_bonus"
            )

            if success:
                logging.info(f"[BONUS_DRAW] ✅ Logging réussi pour {self.user.display_name}")
            else:
                logging.error(f"[BONUS_DRAW] ❌ Échec du logging pour {self.user.display_name}")
        else:
            logging.error(f"[BONUS_DRAW] ❌ Logging manager non disponible pour {self.user.display_name}")

        # 3) Décrémenter un bonus (nouvelle logique)
        success = await self.cog.consume_single_bonus(self.user.id, self.user.display_name)
        if not success:
            logging.error(f"[BONUS_DRAW] ❌ Échec de la consommation du bonus pour {self.user.display_name}")

        # 4) Traiter toutes les vérifications d'upgrade en attente
        await self.cog.process_all_pending_upgrade_checks(interaction, 1361993326215172218)

        return drawn_cards

    @discord.ui.button(label="⚔️ Tirage sacrificiel", style=discord.ButtonStyle.danger, row=0)
    async def sacrificial_draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour le tirage sacrificiel."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        # Vérifier que le tirage se fait dans le bon salon
        if interaction.channel_id != 1361993326215172218:
            await interaction.response.send_message(
                "🚫 Les tirages ne sont autorisés que dans le salon <#1361993326215172218>.",
                ephemeral=True
            )
            return

        # Répondre immédiatement avec un message éphémère
        await interaction.response.send_message(
            "⚔️ **Préparation du tirage sacrificiel...**",
            ephemeral=True
        )

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
                value="Ces cartes seront **définitivement perdues** en échange d'un tirage classique !",
                inline=False
            )

            await interaction.followup.send(embed=embed, view=confirmation_view, ephemeral=True)

        except Exception as e:
            logging.error(f"[SACRIFICIAL_DRAW] Erreur: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors du tirage sacrificiel.",
                ephemeral=True
            )

    @discord.ui.button(label="📚 Ma galerie", style=discord.ButtonStyle.secondary, row=1)
    async def view_gallery(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour voir la galerie de cartes."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Utiliser la méthode de galerie complète
            gallery_embeds = self.cog.generate_gallery_embeds(self.user)

            if not gallery_embeds:
                await interaction.followup.send(
                    "❌ Vous n'avez aucune carte dans votre collection.",
                    ephemeral=True
                )
                return

            # Importer ici pour éviter les imports circulaires
            from .gallery_views import GalleryView

            # Créer la vue de galerie complète
            gallery_view = GalleryView(self.cog, self.user)
            await interaction.followup.send(embeds=gallery_embeds, view=gallery_view, ephemeral=True)
            
        except Exception as e:
            logging.error(f"[MENU] Erreur lors de l'affichage de la galerie: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de l'affichage de la galerie.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Échanges", style=discord.ButtonStyle.secondary, row=1)
    async def trading_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour accéder au menu des échanges."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)

        try:
            from .trade_views import ExchangeBoardView

            board_view = ExchangeBoardView(self.cog, self.user, interaction.guild)

            embed = discord.Embed(
                title="🔄 Tableau d'échanges",
                description="Déposez une carte ou échangez-en une avec un autre joueur.",
                color=0x3498db
            )

            await interaction.followup.send(embed=embed, view=board_view, ephemeral=True)

        except Exception as e:
            logging.error(f"[MENU] Erreur lors de l'affichage du menu d'échange: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de l'affichage du menu d'échange.",
                ephemeral=True
            )
    
# Ancien bouton tirage sacrificiel supprimé - maintenant placé après le tirage journalier

    @discord.ui.button(label="🏆 Classement", style=discord.ButtonStyle.secondary, row=2)
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
        
        # Répondre immédiatement avec un message éphémère
        await interaction.response.send_message(
            "⚔️ **Sacrifice en cours...**",
            ephemeral=True
        )
        
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

            # Effectuer un tirage classique de 3 cartes (comme le tirage journalier)
            drawn_cards = self.cog.drawing_manager.draw_cards(3)

            if drawn_cards:
                # Créer un embed principal pour le sacrifice accompli
                embed = discord.Embed(
                    title="⚔️ Sacrifice accompli !",
                    description=f"Vous avez obtenu **{len(drawn_cards)} cartes** :",
                    color=0x27ae60
                )

                # Ajouter chaque carte tirée à l'embed
                for i, (cat, name) in enumerate(drawn_cards, 1):
                    display_name = name.removesuffix('.png')
                    is_full = "(Full)" in name

                    card_info = f"**{display_name}** ({cat})"
                    if is_full:
                        card_info += " ✨ *Variante Full !*"

                    embed.add_field(
                        name=f"Carte {i}",
                        value=card_info,
                        inline=True
                    )

                # Affichage des cartes avec embeds/images (style original) - AVANT ajout à l'inventaire
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
                        if file_bytes:
                            embed, image_file = self.cog.build_card_embed(cat, name, file_bytes, self.user)
                            embed_msgs.append((embed, image_file))

                if embed_msgs:
                    # Envoyer toutes les cartes directement dans le salon comme messages indépendants
                    for embed, image_file in embed_msgs:
                        await interaction.channel.send(embed=embed, file=image_file)
                else:
                    # Si aucune carte n'a été tirée, afficher un message d'erreur éphémère
                    await interaction.followup.send(
                        "❌ Aucune carte n'a pu être tirée.",
                        ephemeral=True
                    )

                # ——————————— COMMIT ———————————
                # Logger le sacrifice de cartes
                if self.cog.storage.logging_manager:
                    logging.info(f"[SACRIFICIAL_DRAW] Tentative de logging pour {self.user.display_name} ({self.user.id})")
                    logging.info(f"[SACRIFICIAL_DRAW] Cartes sacrifiées: {self.selected_cards}")
                    logging.info(f"[SACRIFICIAL_DRAW] Cartes reçues: {drawn_cards}")

                    success = self.cog.storage.logging_manager.log_card_sacrifice(
                        user_id=self.user.id,
                        user_name=self.user.display_name,
                        sacrificed_cards=self.selected_cards,
                        received_cards=drawn_cards,
                        source="tirage_sacrificiel"
                    )

                    if success:
                        logging.info(f"[SACRIFICIAL_DRAW] ✅ Logging réussi pour {self.user.display_name}")
                    else:
                        logging.error(f"[SACRIFICIAL_DRAW] ❌ Échec du logging pour {self.user.display_name}")
                else:
                    logging.error(f"[SACRIFICIAL_DRAW] ❌ Logging manager non disponible pour {self.user.display_name}")

                # Maintenant ajouter les cartes tirées à l'inventaire
                for cat, name in drawn_cards:
                    self.cog.add_card_to_user(self.user.id, cat, name,
                                            user_name=self.user.display_name,
                                            source="tirage_sacrificiel")

                # Enregistrer le tirage sacrificiel (ceci marque l'utilisateur pour vérification)
                self.cog.drawing_manager.record_sacrificial_draw(self.user.id)

                # Traiter toutes les vérifications d'upgrade en attente
                await self.cog.process_all_pending_upgrade_checks(interaction, 1361993326215172218)

                # Annonce publique et mur des cartes
                await self.cog._handle_announce_and_wall(interaction, drawn_cards)
            else:
                await interaction.followup.send(
                    "❌ Aucune carte rare disponible.",
                    ephemeral=True
                )

            # Désactiver tous les boutons
            for child in self.children:
                child.disabled = True
            
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
