"""
Vues pour les échanges de cartes.
"""

import discord
import logging
from typing import TYPE_CHECKING, List, Tuple, Optional

if TYPE_CHECKING:
    from ...Cards import Cards


class TradeMenuView(discord.ui.View):
    """Menu principal des échanges."""
    
    def __init__(self, cog: "Cards", user: discord.User):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user
    
    @discord.ui.button(label="Déposer une carte", style=discord.ButtonStyle.primary, row=0)
    async def deposit_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour déposer une carte dans le vault."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        # Importer ici pour éviter les imports circulaires
        from .modal_views import DepositCardModal
        
        modal = DepositCardModal(self.cog, self.user)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Retirer mes cartes", style=discord.ButtonStyle.secondary, row=0)
    async def withdraw_cards(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour retirer toutes les cartes du vault."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Récupérer les cartes uniques du vault
            unique_vault_cards = self.cog.vault_manager.get_unique_vault_cards(self.user.id)
            
            if not unique_vault_cards:
                await interaction.followup.send(
                    "❌ Vous n'avez aucune carte dans le vault.",
                    ephemeral=True
                )
                return
            
            # Créer la vue de confirmation
            confirmation_view = WithdrawVaultConfirmationView(self.cog, self.user, unique_vault_cards)
            
            # Créer l'embed
            embed = discord.Embed(
                title="📤 Retirer les cartes du vault",
                description=f"Vous avez **{len(unique_vault_cards)}** cartes uniques dans le vault.",
                color=0xf39c12
            )
            
            # Afficher quelques cartes en exemple
            if len(unique_vault_cards) <= 10:
                card_list = "\n".join([
                    f"• **{name.removesuffix('.png')}** ({cat})"
                    for cat, name in unique_vault_cards
                ])
            else:
                card_list = "\n".join([
                    f"• **{name.removesuffix('.png')}** ({cat})"
                    for cat, name in unique_vault_cards[:10]
                ])
                card_list += f"\n... et {len(unique_vault_cards) - 10} autres"
            
            embed.add_field(
                name="Cartes dans le vault",
                value=card_list,
                inline=False
            )
            
            await interaction.followup.send(embed=embed, view=confirmation_view, ephemeral=True)
            
        except Exception as e:
            logging.error(f"[TRADE] Erreur lors du retrait: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors du retrait.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Initier un échange", style=discord.ButtonStyle.success, row=1)
    async def initiate_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour initier un échange avec un autre utilisateur."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        # Importer ici pour éviter les imports circulaires
        from .modal_views import InitiateTradeModal
        
        modal = InitiateTradeModal(self.cog, self.user)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="👀 Voir mon coffre", style=discord.ButtonStyle.secondary, row=1)
    async def view_vault(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour voir le contenu du coffre."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            vault_cards = self.cog.vault_manager.get_user_vault_cards(self.user.id)
            if not vault_cards:
                await interaction.followup.send("📦 Votre coffre est vide.", ephemeral=True)
                return

            # Grouper les cartes par catégorie et compter
            cards_by_cat = {}
            for cat, name in vault_cards:
                cards_by_cat.setdefault(cat, []).append(name)

            embed = discord.Embed(
                title=f"📦 Coffre de {self.user.display_name}",
                color=0x8B4513
            )

            # Trier les catégories selon l'ordre de rareté
            rarity_order = ["Secrète", "Fondateur", "Historique", "Maître", "Black Hole",
                           "Architectes", "Professeurs", "Autre", "Élèves"]

            for cat in rarity_order:
                if cat in cards_by_cat:
                    names = cards_by_cat[cat]
                    # Compter les occurrences
                    counts = {}
                    for name in names:
                        counts[name] = counts.get(name, 0) + 1

                    # Créer la liste formatée
                    card_list = []
                    for name, count in sorted(counts.items()):
                        display_name = name.removesuffix('.png')
                        card_id = self.cog.get_card_identifier(cat, name)
                        identifier_text = f" ({card_id})" if card_id else ""
                        count_text = f' (x{count})' if count > 1 else ''
                        card_list.append(f"• **{display_name}**{identifier_text}{count_text}")

                    embed.add_field(
                        name=f"📂 {cat}",
                        value="\n".join(card_list),
                        inline=False
                    )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f"[VAULT_VIEW] Erreur lors de l'affichage du coffre: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de l'affichage du coffre.",
                ephemeral=True
            )


class WithdrawVaultConfirmationView(discord.ui.View):
    """Vue de confirmation pour retirer les cartes du vault."""
    
    def __init__(self, cog: "Cards", user: discord.User, unique_vault_cards: List[Tuple[str, str]]):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user
        self.unique_vault_cards = unique_vault_cards
    
    @discord.ui.button(label="Confirmer le retrait", style=discord.ButtonStyle.danger)
    async def confirm_withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirme le retrait de toutes les cartes du vault."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Récupérer toutes les cartes du vault (avec doublons)
            vault_cards = self.cog.vault_manager.get_user_vault_cards(self.user.id)
            
            if not vault_cards:
                await interaction.followup.send(
                    "❌ Votre vault est déjà vide.",
                    ephemeral=True
                )
                return
            
            # Transférer toutes les cartes vers l'inventaire
            success_count = 0
            for cat, name in vault_cards:
                if self.cog.add_card_to_user(self.user.id, cat, name):
                    if self.cog.vault_manager.remove_card_from_vault(self.user.id, cat, name):
                        success_count += 1
                    else:
                        # Rollback si échec du retrait du vault
                        self.cog.remove_card_from_user(self.user.id, cat, name)
            
            if success_count == len(vault_cards):
                embed = discord.Embed(
                    title="✅ Retrait réussi",
                    description=f"**{success_count}** cartes ont été transférées de votre vault vers votre inventaire.",
                    color=0x27ae60
                )
            else:
                embed = discord.Embed(
                    title="⚠️ Retrait partiel",
                    description=f"**{success_count}/{len(vault_cards)}** cartes ont été transférées.",
                    color=0xf39c12
                )
            
            # Traiter toutes les vérifications d'upgrade en attente
            await self.cog.process_all_pending_upgrade_checks(interaction, 1361993326215172218)

            # Désactiver tous les boutons
            for child in self.children:
                child.disabled = True

            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"[VAULT] Erreur lors du retrait: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors du retrait.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Annule le retrait."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        # Désactiver tous les boutons
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(
            content="❌ Retrait annulé.",
            embed=None,
            view=self
        )





class TradeConfirmationView(discord.ui.View):
    """Vue pour la confirmation d'échange avec double validation."""

    def __init__(self, cog: "Cards", initiator: discord.User, target: discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.initiator = initiator
        self.target = target
        self.target_confirmed = False
        self.trade_executed = False

    @discord.ui.button(label="✅ Confirmer l'échange", style=discord.ButtonStyle.success)
    async def confirm_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirme l'échange (première étape - destinataire)."""
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "Vous n'êtes pas le destinataire de cette proposition.", ephemeral=True
            )
            return

        if self.target_confirmed:
            await interaction.response.send_message(
                "⚠️ Vous avez déjà confirmé cet échange.", ephemeral=True
            )
            return

        self.target_confirmed = True

        # Désactiver les boutons immédiatement
        for child in self.children:
            child.disabled = True

        await interaction.response.send_message(
            "✅ Vous avez accepté l'échange complet. En attente de la confirmation de l'initiateur.",
            ephemeral=True
        )

        # Notifier l'initiateur et lui demander confirmation
        try:
            # Récupérer les cartes des deux coffres pour l'affichage
            initiator_vault_cards = self.cog.vault_manager.get_user_vault_cards(self.initiator.id)
            target_vault_cards = self.cog.vault_manager.get_user_vault_cards(self.target.id)

            # Créer l'embed de confirmation finale pour l'initiateur
            embed = discord.Embed(
                title="🔔 Confirmation finale requise",
                description=f"**{self.target.display_name}** a accepté l'échange complet !\n\n**Confirmez-vous cet échange ?**",
                color=0x00ff00
            )

            # Afficher les cartes qui seront échangées
            initiator_unique = list({(cat, name) for cat, name in initiator_vault_cards})
            target_unique = list({(cat, name) for cat, name in target_vault_cards})

            # Cartes que l'initiateur donne
            give_text = "\n".join([f"- **{name.removesuffix('.png')}** (*{cat}*)" for cat, name in initiator_unique])

            embed.add_field(
                name=f"📤 Vous donnez ({len(initiator_unique)} cartes uniques)",
                value=give_text if give_text else "Aucune carte",
                inline=False
            )

            # Cartes que l'initiateur reçoit
            receive_text = "\n".join([f"- **{name.removesuffix('.png')}** (*{cat}*)" for cat, name in target_unique])

            embed.add_field(
                name=f"📥 Vous recevez ({len(target_unique)} cartes uniques)",
                value=receive_text if receive_text else "Aucune carte",
                inline=False
            )

            view = InitiatorFinalConfirmationView(self.cog, self.initiator, self.target)
            await self.initiator.send(embed=embed, view=view)

            # Feedback supplémentaire pour confirmer que le DM a été envoyé
            await interaction.followup.send(
                f"📨 Demande de confirmation finale envoyée à {self.initiator.display_name} en message privé.",
                ephemeral=True
            )

        except discord.Forbidden:
            # Si impossible d'envoyer en DM, créer un message public
            embed.description = f"{self.initiator.mention}, **{self.target.display_name}** a accepté l'échange complet !\n\n**Confirmez-vous cet échange ?**"
            view = InitiatorFinalConfirmationView(self.cog, self.initiator, self.target)
            await interaction.followup.send(embed=embed, view=view, ephemeral=False)

    @discord.ui.button(label="❌ Refuser l'échange", style=discord.ButtonStyle.danger)
    async def decline_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refuse l'échange."""
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "Vous n'êtes pas le destinataire de cette proposition.", ephemeral=True
            )
            return

        if self.target_confirmed:
            await interaction.response.send_message(
                "⚠️ Vous avez déjà traité cette proposition.", ephemeral=True
            )
            return

        self.target_confirmed = True  # Marquer comme traité

        # Désactiver tous les boutons immédiatement
        for child in self.children:
            child.disabled = True

        await interaction.response.send_message("❌ Échange refusé.", ephemeral=True)

        try:
            await self.initiator.send(
                f"**{self.target.display_name}** a refusé votre proposition d'échange complet."
            )
        except discord.Forbidden:
            pass


class InitiatorFinalConfirmationView(discord.ui.View):
    """Vue pour la confirmation finale de l'initiateur."""

    def __init__(self, cog: "Cards", initiator: discord.User, target: discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.initiator = initiator
        self.target = target
        self.trade_executed = False

    @discord.ui.button(label="✅ Confirmer l'échange complet", style=discord.ButtonStyle.success)
    async def confirm_final_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirme et exécute l'échange final."""
        if interaction.user.id != self.initiator.id:
            await interaction.response.send_message(
                "Vous n'êtes pas l'initiateur de cet échange.", ephemeral=True
            )
            return

        # Éviter les exécutions multiples
        if self.trade_executed:
            await interaction.response.send_message(
                "⚠️ Cet échange a déjà été traité.", ephemeral=True
            )
            return

        # Répondre IMMÉDIATEMENT à l'interaction
        await interaction.response.send_message(
            "⏳ Traitement de l'échange en cours...", ephemeral=True
        )

        # Marquer comme en cours de traitement
        self.trade_executed = True

        # Désactiver tous les boutons IMMÉDIATEMENT
        for child in self.children:
            child.disabled = True

        # Exécuter l'échange complet des coffres
        success = await self.execute_full_vault_trade(interaction)

        # Mettre à jour le message de statut selon le résultat
        if success:
            await interaction.edit_original_response(content="✅ Échange terminé avec succès !")
        else:
            await interaction.edit_original_response(content="❌ Échec de l'échange.")
            # Réactiver les boutons en cas d'échec
            self.trade_executed = False
            for child in self.children:
                child.disabled = False

    @discord.ui.button(label="❌ Annuler l'échange", style=discord.ButtonStyle.danger)
    async def cancel_final_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Annule l'échange final."""
        if interaction.user.id != self.initiator.id:
            await interaction.response.send_message(
                "Vous n'êtes pas l'initiateur de cet échange.", ephemeral=True
            )
            return

        if self.trade_executed:
            await interaction.response.send_message(
                "⚠️ Cet échange a déjà été traité.", ephemeral=True
            )
            return

        self.trade_executed = True

        # Désactiver tous les boutons immédiatement
        for child in self.children:
            child.disabled = True

        await interaction.response.send_message("❌ Échange annulé.", ephemeral=True)

        try:
            await self.target.send(
                f"**{self.initiator.display_name}** a annulé l'échange complet."
            )
        except discord.Forbidden:
            pass

    async def execute_full_vault_trade(self, interaction: discord.Interaction) -> bool:
        """Exécute l'échange complet des coffres entre les deux utilisateurs."""
        try:
            # Récupérer les cartes des deux coffres
            initiator_vault_cards = self.cog.vault_manager.get_user_vault_cards(self.initiator.id)
            target_vault_cards = self.cog.vault_manager.get_user_vault_cards(self.target.id)

            if not initiator_vault_cards or not target_vault_cards:
                await interaction.followup.send(
                    "❌ Un des coffres est vide. L'échange ne peut pas avoir lieu.",
                    ephemeral=True
                )
                return False

            # Étape 1: Retirer toutes les cartes des coffres
            initiator_removed_cards = []
            target_removed_cards = []

            # Retirer les cartes uniques du coffre de l'initiateur
            for cat, name in set(initiator_vault_cards):
                if self.cog.vault_manager.remove_card_from_vault(self.initiator.id, cat, name):
                    initiator_removed_cards.append((cat, name))
                else:
                    # Rollback en cas d'échec
                    for rollback_cat, rollback_name in initiator_removed_cards:
                        self.cog.vault_manager.add_card_to_vault(self.initiator.id, rollback_cat, rollback_name, skip_possession_check=True)
                    return False

            # Retirer les cartes uniques du coffre de la cible
            for cat, name in set(target_vault_cards):
                if self.cog.vault_manager.remove_card_from_vault(self.target.id, cat, name):
                    target_removed_cards.append((cat, name))
                else:
                    # Rollback complet en cas d'échec
                    for rollback_cat, rollback_name in initiator_removed_cards:
                        self.cog.vault_manager.add_card_to_vault(self.initiator.id, rollback_cat, rollback_name, skip_possession_check=True)
                    for rollback_cat, rollback_name in target_removed_cards:
                        self.cog.vault_manager.add_card_to_vault(self.target.id, rollback_cat, rollback_name, skip_possession_check=True)
                    return False

            # Étape 2: Ajouter les cartes aux inventaires principaux
            # Ajouter les cartes de la cible à l'inventaire de l'initiateur
            for cat, name in target_removed_cards:
                if not self.cog.add_card_to_user(self.initiator.id, cat, name):
                    # Rollback complet
                    await self.rollback_full_trade(initiator_removed_cards, target_removed_cards)
                    return False

            # Ajouter les cartes de l'initiateur à l'inventaire de la cible
            for cat, name in initiator_removed_cards:
                if not self.cog.add_card_to_user(self.target.id, cat, name):
                    # Rollback complet
                    await self.rollback_full_trade(initiator_removed_cards, target_removed_cards)
                    return False

            # Étape 3: Notifier les utilisateurs
            try:
                await self.initiator.send(
                    f"📦 Échange confirmé ! Vous avez échangé {len(initiator_removed_cards)} cartes avec **{self.target.display_name}**."
                )
                await self.target.send(
                    f"📦 Échange confirmé ! Vous avez échangé {len(target_removed_cards)} cartes avec **{self.initiator.display_name}**."
                )
            except discord.Forbidden:
                pass

            # Étape 4: Traiter toutes les vérifications d'upgrade en attente
            try:
                await self.cog.process_all_pending_upgrade_checks(interaction, 1361993326215172218)
                logging.info(f"[VAULT_TRADE] Vérifications de conversion terminées pour les utilisateurs {self.initiator.id} et {self.target.id}")
            except Exception as e:
                logging.error(f"[VAULT_TRADE] Erreur lors de la vérification des conversions après échange de coffres: {e}")
                # Ne pas faire échouer l'échange si les conversions échouent

            return True

        except Exception as e:
            logging.error(f"Erreur lors de l'échange complet: {e}")
            return False

    async def rollback_full_trade(self, initiator_cards, target_cards):
        """Rollback complet en cas d'échec de l'échange."""
        for cat, name in initiator_cards:
            self.cog.vault_manager.add_card_to_vault(self.initiator.id, cat, name, skip_possession_check=True)
        for cat, name in target_cards:
            self.cog.vault_manager.add_card_to_vault(self.target.id, cat, name, skip_possession_check=True)



class ExchangeBoardView(discord.ui.View):
    """Vue pour afficher et interagir avec le tableau d'échanges."""

    def __init__(self, cog: "Cards", user: discord.User, guild: Optional[discord.Guild]):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user
        self.guild = guild

        offers = self.cog.trading_manager.list_board_offers()
        self.pages: List[List[discord.SelectOption]] = []
        for i in range(0, len(offers), 25):
            page: List[discord.SelectOption] = []
            for o in offers[i:i + 25]:
                owner_id = int(o["owner"])
                member = self.guild.get_member(owner_id) if self.guild else None
                if member:
                    owner_name = member.display_name
                else:
                    user_obj = self.cog.bot.get_user(owner_id) if hasattr(self.cog, "bot") else None
                    owner_name = user_obj.display_name if user_obj else str(owner_id)
                page.append(
                    discord.SelectOption(
                        label=f"{o['name'].removesuffix('.png')} ({o['cat']})",
                        description=f"ID {o['id']} - Proposé par {owner_name}",
                        value=str(o['id'])
                    )
                )
            self.pages.append(page)

        if not self.pages:
            self.pages = [[discord.SelectOption(label="Aucune offre", value="0")]]

        self.current_page = 0
        self.offer_select = discord.ui.Select(
            placeholder=f"Offres disponibles (1/{len(self.pages)})" if self.pages else "Offres disponibles",
            options=self.pages[self.current_page],
        )

        async def offer_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("Vous ne pouvez pas utiliser ce menu.", ephemeral=True)
                return
            selected = self.offer_select.values[0]
            if selected == "0":
                await interaction.response.send_message("Aucune offre disponible.", ephemeral=True)
                return
            board_id = int(selected)
            from .modal_views import OfferCardModal
            modal = OfferCardModal(self.cog, self.user, board_id)
            await interaction.response.send_modal(modal)

        self.offer_select.callback = offer_callback
        self.add_item(self.offer_select)

        if len(self.pages) > 1:
            self.prev_button = discord.ui.Button(label="◀️", style=discord.ButtonStyle.secondary, row=2)
            self.next_button = discord.ui.Button(label="▶️", style=discord.ButtonStyle.secondary, row=2)
            self.prev_button.callback = self._prev_page
            self.next_button.callback = self._next_page
            self.prev_button.disabled = True
            self.add_item(self.prev_button)
            self.add_item(self.next_button)

    @discord.ui.button(label="Déposer une carte", style=discord.ButtonStyle.primary, row=1)
    async def deposit_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        from .modal_views import BoardDepositModal
        modal = BoardDepositModal(self.cog, self.user)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Retirer une carte", style=discord.ButtonStyle.danger, row=1)
    async def withdraw_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return

        offers = [o for o in self.cog.trading_manager.list_board_offers() if int(o["owner"]) == self.user.id]
        if not offers:
            await interaction.response.send_message("Vous n'avez aucune carte sur le tableau.", ephemeral=True)
            return

        options = [
            discord.SelectOption(
                label=f"{o['name'].removesuffix('.png')} ({o['cat']})",
                description=f"ID {o['id']}",
                value=str(o['id'])
            )
            for o in offers[:25]
        ]

        select = discord.ui.Select(placeholder="Sélectionnez l'offre à retirer", options=options)
        view = discord.ui.View()
        view.add_item(select)

        async def cb(inter: discord.Interaction):
            if inter.user.id != self.user.id:
                await inter.response.send_message("Vous ne pouvez pas utiliser ce menu.", ephemeral=True)
                return
            board_id = int(select.values[0])
            success = self.cog.trading_manager.withdraw_from_board(self.user.id, board_id)
            if success:
                await inter.response.send_message("Carte retirée du tableau.", ephemeral=True)
            else:
                await inter.response.send_message("Impossible de retirer la carte.", ephemeral=True)
            view.stop()

        select.callback = cb
        await interaction.response.send_message("Choisissez la carte à retirer :", view=view, ephemeral=True)

    async def _prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
        self.offer_select.options = self.pages[self.current_page]
        self.offer_select.placeholder = f"Offres disponibles ({self.current_page + 1}/{len(self.pages)})"
        if hasattr(self, 'prev_button'):
            self.prev_button.disabled = self.current_page == 0
            self.next_button.disabled = self.current_page == len(self.pages) - 1
        await interaction.response.edit_message(view=self)

    async def _next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
        self.offer_select.options = self.pages[self.current_page]
        self.offer_select.placeholder = f"Offres disponibles ({self.current_page + 1}/{len(self.pages)})"
        if hasattr(self, 'prev_button'):
            self.prev_button.disabled = self.current_page == 0
            self.next_button.disabled = self.current_page == len(self.pages) - 1
        await interaction.response.edit_message(view=self)

class BoardTradeRequestView(discord.ui.View):
    """Vue envoyée au propriétaire pour confirmer ou refuser l'échange."""

    def __init__(self, cog: "Cards", buyer_id: int, board_id: int,
                 offered_cards: List[Tuple[str, str]]):
        super().__init__(timeout=24 * 60 * 60)
        self.cog = cog
        self.buyer_id = buyer_id
        self.board_id = board_id
        self.offered_cards = offered_cards

    async def notify_buyer(self, message: str) -> None:
        try:
            user = await self.cog.bot.fetch_user(self.buyer_id)
            await user.send(message)
        except Exception:
            pass

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        success = self.cog.trading_manager.take_from_board(
            self.buyer_id, self.board_id, self.offered_cards
        )
        if success:
            await interaction.followup.send("✅ Échange réalisé avec succès.", ephemeral=True)
            await self.notify_buyer("✅ Votre offre a été acceptée !")
            try:
                await self.cog.process_all_pending_upgrade_checks(interaction, 1361993326215172218)
            except Exception as e:
                logging.error(f"[BOARD_TRADE] Erreur lors de la vérification des conversions: {e}")
        else:
            await interaction.followup.send("❌ Échange impossible.", ephemeral=True)
            await self.notify_buyer("❌ Votre offre a échoué.")
        self.stop()

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Offre refusée.", ephemeral=True)
        await self.notify_buyer("❌ Votre offre a été refusée.")
        self.stop()

    async def on_timeout(self) -> None:
        await self.notify_buyer("⌛ L'offre a expiré sans réponse.")




class TradeFinalConfirmView(discord.ui.View):
    """Vue finale pour confirmer ou refuser un échange de cartes."""

    def __init__(self, cog: "Cards", offerer: discord.User, target: discord.User,
                 offer_cards: List[Tuple[str, str]], return_cards: List[Tuple[str, str]]):
        super().__init__(timeout=120)
        self.cog = cog
        self.offerer = offerer
        self.target = target
        self.offer_cards = offer_cards
        self.return_cards = return_cards

    async def _notify(self, user_id: int, message: str) -> None:
        try:
            user = await self.cog.bot.fetch_user(user_id)
            await user.send(message)
        except Exception:
            pass

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if interaction.user.id not in {self.offerer.id, self.target.id}:
            await interaction.followup.send("Vous ne pouvez pas confirmer cet échange.", ephemeral=True)
            return
        success = self.cog.trading_manager.safe_exchange(
            self.offerer.id, self.target.id, self.offer_cards, self.return_cards
        )
        if success:
            await interaction.followup.send("✅ Échange réalisé avec succès.", ephemeral=True)
            await self._notify(self.offerer.id, "✅ Échange complété.")
            await self._notify(self.target.id, "✅ Échange complété.")
        else:
            await interaction.followup.send("❌ Échange impossible.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Échange annulé.", ephemeral=True)
        await self._notify(self.offerer.id, "❌ Échange refusé.")
        await self._notify(self.target.id, "❌ Échange refusé.")
        self.stop()
