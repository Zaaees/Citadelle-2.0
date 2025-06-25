"""
Vues pour les échanges de cartes.
"""

import discord
import logging
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from ...Cards import Cards


class TradeMenuView(discord.ui.View):
    """Menu principal des échanges."""
    
    def __init__(self, cog: "Cards", user: discord.User):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user
    
    @discord.ui.button(label="Déposer une carte", style=discord.ButtonStyle.primary)
    async def deposit_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour déposer une carte dans le vault."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        # Importer ici pour éviter les imports circulaires
        from .modal_views import DepositCardModal
        
        modal = DepositCardModal(self.cog, self.user)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Retirer mes cartes", style=discord.ButtonStyle.secondary)
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
    
    @discord.ui.button(label="Initier un échange", style=discord.ButtonStyle.success)
    async def initiate_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton pour initier un échange avec un autre utilisateur."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser ce bouton.", ephemeral=True)
            return
        
        # Importer ici pour éviter les imports circulaires
        from .modal_views import InitiateTradeModal
        
        modal = InitiateTradeModal(self.cog, self.user)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="👀 Voir mon coffre", style=discord.ButtonStyle.secondary)
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


class TradeRequestView(discord.ui.View):
    """Vue pour accepter ou refuser une demande d'échange."""
    
    def __init__(self, cog: "Cards", initiator: discord.User, target: discord.User):
        super().__init__(timeout=300)  # 5 minutes
        self.cog = cog
        self.initiator = initiator
        self.target = target
    
    @discord.ui.button(label="Accepter l'échange", style=discord.ButtonStyle.success)
    async def accept_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Accepte la demande d'échange."""
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "Seul le destinataire peut accepter cet échange.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Vérifier que les deux utilisateurs ont des cartes dans leur vault
            initiator_vault = self.cog.vault_manager.get_user_vault_cards(self.initiator.id)
            target_vault = self.cog.vault_manager.get_user_vault_cards(self.target.id)
            
            if not initiator_vault:
                await interaction.followup.send(
                    f"❌ {self.initiator.display_name} n'a aucune carte dans son vault.",
                    ephemeral=True
                )
                return
            
            if not target_vault:
                await interaction.followup.send(
                    "❌ Vous n'avez aucune carte dans votre vault.",
                    ephemeral=True
                )
                return
            
            # Créer la vue de confirmation finale
            confirmation_view = FullVaultTradeConfirmationView(self.cog, self.initiator, self.target)
            
            # Créer l'embed de confirmation
            embed = discord.Embed(
                title="🔄 Confirmation d'échange de vault",
                description="Échange complet des vaults entre :",
                color=0x3498db
            )
            
            embed.add_field(
                name=f"📦 Vault de {self.initiator.display_name}",
                value=f"{len(set(initiator_vault))} cartes uniques\n({len(initiator_vault)} total)",
                inline=True
            )
            
            embed.add_field(
                name=f"📦 Vault de {self.target.display_name}",
                value=f"{len(set(target_vault))} cartes uniques\n({len(target_vault)} total)",
                inline=True
            )
            
            embed.add_field(
                name="⚠️ Attention",
                value="Cet échange est **irréversible** ! Tous les contenus des vaults seront échangés.",
                inline=False
            )
            
            # Désactiver tous les boutons de cette vue
            for child in self.children:
                child.disabled = True
            
            await interaction.followup.send(embed=embed, view=confirmation_view, ephemeral=True)
            
        except Exception as e:
            logging.error(f"[TRADE] Erreur lors de l'acceptation: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de l'acceptation.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Refuser l'échange", style=discord.ButtonStyle.danger)
    async def refuse_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refuse la demande d'échange."""
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "Seul le destinataire peut refuser cet échange.",
                ephemeral=True
            )
            return
        
        # Désactiver tous les boutons
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(
            content=f"❌ {self.target.display_name} a refusé l'échange.",
            embed=None,
            view=self
        )


class FullVaultTradeConfirmationView(discord.ui.View):
    """Vue de confirmation finale pour l'échange complet de vault."""
    
    def __init__(self, cog: "Cards", initiator: discord.User, target: discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.initiator = initiator
        self.target = target
        self.trade_executed = False
    
    @discord.ui.button(label="Confirmer l'échange", style=discord.ButtonStyle.success)
    async def confirm_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirme et exécute l'échange de vault."""
        # Vérifier que l'utilisateur est l'un des participants
        if interaction.user.id not in [self.initiator.id, self.target.id]:
            await interaction.response.send_message(
                "Seuls les participants peuvent confirmer cet échange.",
                ephemeral=True
            )
            return
        
        # Éviter les doubles exécutions
        if self.trade_executed:
            await interaction.response.send_message(
                "Cet échange a déjà été traité.",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            "🔄 Échange en cours de traitement...",
            ephemeral=True
        )
        
        # Marquer comme en cours de traitement APRÈS avoir répondu
        self.trade_executed = True
        
        # Désactiver tous les boutons IMMÉDIATEMENT
        for child in self.children:
            child.disabled = True
        
        # Exécuter l'échange complet des vaults
        success = await self.execute_full_vault_trade(interaction)
        
        # Mettre à jour le message de statut selon le résultat
        if success:
            await interaction.edit_original_response(content="✅ Échange terminé avec succès !")
        else:
            await interaction.edit_original_response(content="❌ Échec de l'échange.")
            # Réactiver les boutons en cas d'échec pour permettre une nouvelle tentative
            self.trade_executed = False
            for child in self.children:
                child.disabled = False
    
    async def execute_full_vault_trade(self, interaction: discord.Interaction) -> bool:
        """Exécute l'échange complet des vaults."""
        try:
            success = self.cog.trading_manager.execute_full_vault_trade(
                self.initiator.id, self.target.id
            )
            
            if success:
                logging.info(f"[TRADE] Échange de vault réussi entre {self.initiator.id} et {self.target.id}")
            else:
                logging.error(f"[TRADE] Échec de l'échange de vault entre {self.initiator.id} et {self.target.id}")
            
            return success
            
        except Exception as e:
            logging.error(f"[TRADE] Erreur lors de l'exécution de l'échange: {e}")
            return False
    
    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Annule l'échange."""
        if interaction.user.id not in [self.initiator.id, self.target.id]:
            await interaction.response.send_message(
                "Seuls les participants peuvent annuler cet échange.",
                ephemeral=True
            )
            return
        
        # Désactiver tous les boutons
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(
            content="❌ Échange annulé.",
            embed=None,
            view=self
        )


class TradeConfirmView(discord.ui.View):
    """Vue de confirmation pour un échange de carte individuelle."""

    def __init__(self, cog: "Cards", offerer: discord.User, target: discord.User, card_category: str, card_name: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.offerer = offerer
        self.target = target
        self.card_category = card_category
        self.card_name = card_name

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Accepte la proposition d'échange."""
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Vous n'êtes pas l'utilisateur visé par cet échange.", ephemeral=True)
            return

        # Importer ici pour éviter les imports circulaires
        from .modal_views import TradeResponseModal

        modal = TradeResponseModal(self.cog, self.offerer, self.target, self.card_category, self.card_name)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refuse la proposition d'échange."""
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Vous n'êtes pas le destinataire de cette proposition.", ephemeral=True)
            return

        # Désactiver tous les boutons
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content="❌ Échange refusé.",
            embed=None,
            view=self
        )


class TradeFinalConfirmView(discord.ui.View):
    """Vue de confirmation finale pour un échange de cartes individuelles."""

    def __init__(self, cog: "Cards", offerer: discord.User, target: discord.User,
                 offer_cat: str, offer_name: str, return_cat: str, return_name: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.offerer = offerer
        self.target = target
        self.offer_cat = offer_cat
        self.offer_name = offer_name
        self.return_cat = return_cat
        self.return_name = return_name
        self.confirmed_by_offer = False
        self.confirmed_by_target = False

    @discord.ui.button(label="Confirmer (destinataire)", style=discord.ButtonStyle.success)
    async def confirm_target(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirmation par le destinataire."""
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Vous n'êtes pas le destinataire de l'échange.", ephemeral=True)
            return

        self.confirmed_by_target = True
        await interaction.response.send_message("✅ Vous avez confirmé. En attente du proposeur.", ephemeral=True)

        if self.confirmed_by_offer:
            await self.finalize_exchange(interaction)

    @discord.ui.button(label="Confirmer (proposeur)", style=discord.ButtonStyle.success)
    async def confirm_offer(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirmation par le proposeur."""
        if interaction.user.id != self.offerer.id:
            await interaction.response.send_message("Vous n'êtes pas le proposeur de l'échange.", ephemeral=True)
            return

        self.confirmed_by_offer = True
        await interaction.response.send_message("✅ Vous avez confirmé. En attente du destinataire.", ephemeral=True)

        if self.confirmed_by_target:
            await self.finalize_exchange(interaction)

    async def finalize_exchange(self, interaction: discord.Interaction):
        """Finalise l'échange entre les deux utilisateurs."""
        try:
            success = self.cog.trading_manager.safe_exchange(
                self.offerer.id, self.target.id,
                self.offer_cat, self.offer_name,
                self.return_cat, self.return_name
            )

            if success:
                # Désactiver tous les boutons
                for child in self.children:
                    child.disabled = True

                # Créer l'embed de succès
                embed = discord.Embed(
                    title="✅ Échange réussi !",
                    description=f"Échange terminé entre {self.offerer.display_name} et {self.target.display_name}",
                    color=0x00ff00
                )

                offer_display = self.offer_name.removesuffix('.png')
                return_display = self.return_name.removesuffix('.png')

                offer_id = self.cog.get_card_identifier(self.offer_cat, self.offer_name)
                return_id = self.cog.get_card_identifier(self.return_cat, self.return_name)

                if offer_id:
                    offer_display += f" ({offer_id})"
                if return_id:
                    return_display += f" ({return_id})"

                embed.add_field(
                    name=f"📤 {self.offerer.display_name} a donné",
                    value=f"**{offer_display}** ({self.offer_cat})",
                    inline=True
                )

                embed.add_field(
                    name=f"📥 {self.target.display_name} a donné",
                    value=f"**{return_display}** ({self.return_cat})",
                    inline=True
                )

                await interaction.edit_original_response(embed=embed, view=self)

                logging.info(f"[TRADE] Échange individuel réussi: {self.offerer.id} <-> {self.target.id}")
            else:
                await interaction.followup.send("❌ Échec de l'échange. Vérifiez que vous possédez encore vos cartes.", ephemeral=True)

        except Exception as e:
            logging.error(f"[TRADE] Erreur lors de la finalisation: {e}")
            await interaction.followup.send("❌ Une erreur est survenue lors de l'échange.", ephemeral=True)
