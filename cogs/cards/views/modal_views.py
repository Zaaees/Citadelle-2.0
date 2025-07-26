"""
Modales pour les interactions utilisateur du système de cartes.
"""

import discord
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...Cards import Cards


class DepositCardModal(discord.ui.Modal, title="Déposer une carte"):
    """Modal pour déposer une carte dans le vault."""
    
    card_name = discord.ui.TextInput(
        label="Carte à déposer (nom ou identifiant)",
        placeholder="Ex : Alex (Variante) ou C42",
        required=True,
        max_length=100
    )
    
    def __init__(self, cog: "Cards", user: discord.User):
        super().__init__()
        self.cog = cog
        self.user = user
    
    async def on_submit(self, interaction: discord.Interaction):
        """Traite le dépôt de carte."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            input_text = self.card_name.value.strip()
            
            # Rechercher la carte dans l'inventaire de l'utilisateur
            card_match = self.cog.find_user_card_by_input(self.user.id, input_text)
            
            if not card_match:
                # Générer des suggestions
                suggestions = self.cog.get_user_card_suggestions(self.user.id, input_text)
                error_msg = f"❌ Carte non trouvée dans votre inventaire : **{input_text}**\n"
                error_msg += f"💡 Utilisez le nom exact de la carte ou son identifiant (ex: C42)"

                if suggestions:
                    error_msg += f"\n\n🔍 **Suggestions similaires :**\n"
                    for suggestion in suggestions:
                        error_msg += f"• {suggestion}\n"

                await interaction.followup.send(error_msg, ephemeral=True)
                return
            
            category, name = card_match
            
            # Vérifier que ce n'est pas une carte Full
            if "(Full)" in name:
                await interaction.followup.send(
                    "❌ Les cartes Full ne peuvent pas être déposées dans le vault.",
                    ephemeral=True
                )
                return
            
            # Retirer la carte de l'inventaire
            if not self.cog.remove_card_from_user(self.user.id, category, name):
                await interaction.followup.send(
                    "❌ Erreur lors du retrait de la carte de votre inventaire.",
                    ephemeral=True
                )
                return
            
            # Ajouter la carte au vault
            if self.cog.vault_manager.add_card_to_vault(self.user.id, category, name):
                display_name = name.removesuffix('.png')
                card_id = self.cog.get_card_id(category, name)
                display_text = f"{display_name} ({card_id})" if card_id else display_name
                
                await interaction.followup.send(
                    f"✅ Carte **{display_text}** ({category}) déposée dans le vault !",
                    ephemeral=True
                )
            else:
                # Rollback : remettre la carte dans l'inventaire
                self.cog.add_card_to_user(self.user.id, category, name)
                await interaction.followup.send(
                    "❌ Erreur lors du dépôt dans le vault.",
                    ephemeral=True
                )
                
        except Exception as e:
            logging.error(f"[DEPOSIT] Erreur lors du dépôt: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors du dépôt.",
                ephemeral=True
            )


class InitiateTradeModal(discord.ui.Modal, title="Initier un échange"):
    """Modal pour initier un échange avec un autre utilisateur."""
    
    target_user = discord.ui.TextInput(
        label="Nom d'utilisateur ou ID Discord",
        placeholder="Ex : @username ou 123456789",
        required=True,
        max_length=100
    )
    
    def __init__(self, cog: "Cards", user: discord.User):
        super().__init__()
        self.cog = cog
        self.user = user
    
    async def on_submit(self, interaction: discord.Interaction):
        """Traite l'initiation d'échange."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            target_input = self.target_user.value.strip()
            
            # Rechercher l'utilisateur cible
            target_user = None
            
            # Essayer par ID Discord
            if target_input.isdigit():
                try:
                    target_user = await interaction.client.fetch_user(int(target_input))
                except discord.NotFound:
                    pass
            
            # Essayer par mention
            if target_input.startswith('<@') and target_input.endswith('>'):
                user_id = target_input[2:-1]
                if user_id.startswith('!'):
                    user_id = user_id[1:]
                try:
                    target_user = await interaction.client.fetch_user(int(user_id))
                except (ValueError, discord.NotFound):
                    pass
            
            # Essayer par nom d'utilisateur dans le serveur
            if not target_user and interaction.guild:
                target_user = discord.utils.find(
                    lambda m: m.display_name.lower() == target_input.lower() or 
                             m.name.lower() == target_input.lower(),
                    interaction.guild.members
                )
            
            if not target_user:
                await interaction.followup.send(
                    f"❌ Utilisateur non trouvé : **{target_input}**",
                    ephemeral=True
                )
                return
            
            # Vérifier que ce n'est pas soi-même
            if target_user.id == self.user.id:
                await interaction.followup.send(
                    "❌ Vous ne pouvez pas échanger avec vous-même.",
                    ephemeral=True
                )
                return
            
            # Vérifier que l'utilisateur a des cartes dans son vault
            user_vault = self.cog.vault_manager.get_user_vault_cards(self.user.id)
            if not user_vault:
                await interaction.followup.send(
                    "❌ Vous devez avoir des cartes dans votre vault pour initier un échange.",
                    ephemeral=True
                )
                return
            
            # Vérifier que l'utilisateur cible a des cartes dans son vault
            target_vault = self.cog.vault_manager.get_user_vault_cards(target_user.id)
            if not target_vault:
                await interaction.followup.send(
                    f"❌ {target_user.display_name} n'a pas de cartes dans son vault.",
                    ephemeral=True
                )
                return

            # Créer la vue de confirmation d'échange
            from .trade_views import TradeConfirmationView

            trade_view = TradeConfirmationView(self.cog, self.user, target_user)

            # Créer l'embed détaillé avec les cartes
            embed = discord.Embed(
                title="🔄 Proposition d'échange complet",
                description=f"**{self.user.display_name}** souhaite échanger TOUT le contenu de son coffre avec vous.\n\n**Voulez-vous accepter cet échange ?**",
                color=0x4E5D94
            )

            # Afficher les cartes de l'initiateur (ce que le destinataire va recevoir)
            initiator_unique = list({(cat, name) for cat, name in user_vault})
            give_text = "\n".join([f"- **{name.removesuffix('.png')}** (*{cat}*)" for cat, name in initiator_unique])

            embed.add_field(
                name=f"📥 Vous recevrez ({len(initiator_unique)} cartes uniques)",
                value=give_text if give_text else "Aucune carte",
                inline=False
            )

            # Afficher les cartes du destinataire (ce qu'il va donner)
            target_unique = list({(cat, name) for cat, name in target_vault})
            receive_text = "\n".join([f"- **{name.removesuffix('.png')}** (*{cat}*)" for cat, name in target_unique])

            embed.add_field(
                name=f"📤 Vous donnerez ({len(target_unique)} cartes uniques)",
                value=receive_text if receive_text else "Aucune carte",
                inline=False
            )

            embed.add_field(
                name="⚠️ Important",
                value="Cet échange transfère TOUTES les cartes des deux coffres vers vos inventaires principaux.",
                inline=False
            )

            # Essayer d'envoyer en message privé
            try:
                await target_user.send(embed=embed, view=trade_view)
                await interaction.followup.send(
                    f"📨 Proposition d'échange envoyée à **{target_user.display_name}** en message privé !",
                    ephemeral=True
                )
            except discord.Forbidden:
                # Si impossible d'envoyer en DM, envoyer en public
                await interaction.followup.send(
                    content=f"{target_user.mention}, vous avez reçu une proposition d'échange !",
                    embed=embed,
                    view=trade_view,
                    ephemeral=False
                )
                await interaction.followup.send(
                    "⚠️ Impossible d'envoyer en message privé. La proposition a été envoyée ici.",
                    ephemeral=True
                )
            
        except Exception as e:
            logging.error(f"[TRADE_INIT] Erreur lors de l'initiation: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de l'initiation de l'échange.",
                ephemeral=True
            )




class TradeOfferCardModal(discord.ui.Modal, title="Proposer un échange"):
    """Modal pour proposer un échange de carte individuelle."""
    
    card_name = discord.ui.TextInput(
        label="Carte à échanger (nom ou identifiant)",
        placeholder="Ex : Alex (Variante) ou C42",
        required=True
    )
    
    def __init__(self, cog: "Cards", user: discord.User, target_user: discord.User):
        super().__init__()
        self.cog = cog
        self.user = user
        self.target_user = target_user
    
    async def on_submit(self, interaction: discord.Interaction):
        """Traite la proposition d'échange."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            input_text = self.card_name.value.strip()
            
            # Rechercher la carte dans l'inventaire de l'utilisateur
            card_match = self.cog.find_user_card_by_input(self.user.id, input_text)
            
            if not card_match:
                # Générer des suggestions
                suggestions = self.cog.get_user_card_suggestions(self.user.id, input_text)
                error_msg = f"❌ Carte non trouvée dans votre inventaire : **{input_text}**\n"
                error_msg += f"💡 Utilisez le nom exact de la carte ou son identifiant (ex: C42)"

                if suggestions:
                    error_msg += f"\n\n🔍 **Suggestions similaires :**\n"
                    for suggestion in suggestions:
                        error_msg += f"• {suggestion}\n"

                await interaction.followup.send(error_msg, ephemeral=True)
                return
            
            category, name = card_match
            
            # Vérifier que la cible a des cartes
            target_cards = self.cog.get_user_cards(self.target_user.id)
            if not target_cards:
                await interaction.followup.send(
                    f"❌ {self.target_user.display_name} n'a aucune carte à échanger.",
                    ephemeral=True
                )
                return
            
            # Créer la vue de confirmation
            from .trade_views import TradeConfirmView
            
            confirm_view = TradeConfirmView(self.cog, self.user, self.target_user, category, name)
            
            # Créer l'embed
            display_name = name.removesuffix('.png')
            card_id = self.cog.get_card_id(category, name)
            display_text = f"{display_name} ({card_id})" if card_id else display_name
            
            embed = discord.Embed(
                title="🔄 Proposition d'échange",
                description=f"{self.user.display_name} propose d'échanger :",
                color=0x3498db
            )
            
            embed.add_field(
                name="Carte proposée",
                value=f"**{display_text}** ({category})",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, view=confirm_view, ephemeral=True)
            
        except Exception as e:
            logging.error(f"[TRADE_OFFER] Erreur lors de la proposition: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de la proposition d'échange.",
                ephemeral=True
            )


class TradeResponseModal(discord.ui.Modal, title="Réponse à l'échange"):
    """Modal pour répondre à un échange de carte individuelle."""
    
    card_name = discord.ui.TextInput(
        label="Carte que vous proposez (nom ou identifiant)",
        placeholder="Ex : Alex (Variante) ou C42",
        required=True
    )
    
    def __init__(self, cog: "Cards", offerer: discord.User, target: discord.User, 
                 offer_cat: str, offer_name: str):
        super().__init__()
        self.cog = cog
        self.offerer = offerer
        self.target = target
        self.offer_cat = offer_cat
        self.offer_name = offer_name
    
    async def on_submit(self, interaction: discord.Interaction):
        """Traite la réponse à l'échange."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            input_text = self.card_name.value.strip()
            
            # Rechercher la carte dans l'inventaire de la cible
            card_match = self.cog.find_user_card_by_input(self.target.id, input_text)
            
            if not card_match:
                # Générer des suggestions
                suggestions = self.cog.get_user_card_suggestions(self.target.id, input_text)
                error_msg = f"❌ Carte non trouvée dans votre inventaire : **{input_text}**\n"
                error_msg += f"💡 Utilisez le nom exact de la carte ou son identifiant (ex: C42)"

                if suggestions:
                    error_msg += f"\n\n🔍 **Suggestions similaires :**\n"
                    for suggestion in suggestions:
                        error_msg += f"• {suggestion}\n"

                await interaction.followup.send(error_msg, ephemeral=True)
                return
            
            return_cat, return_name = card_match
            
            # Créer la vue de confirmation finale
            from .trade_views import TradeFinalConfirmView
            
            final_view = TradeFinalConfirmView(
                self.cog, self.offerer, self.target, 
                self.offer_cat, self.offer_name, return_cat, return_name
            )
            
            # Créer l'embed de confirmation
            offer_display = self.offer_name.removesuffix('.png')
            return_display = return_name.removesuffix('.png')
            
            offer_id = self.cog.get_card_id(self.offer_cat, self.offer_name)
            return_id = self.cog.get_card_id(return_cat, return_name)
            
            if offer_id:
                offer_display += f" ({offer_id})"
            if return_id:
                return_display += f" ({return_id})"
            
            embed = discord.Embed(
                title="🔄 Confirmation d'échange",
                description="Récapitulatif de l'échange :",
                color=0x3498db
            )
            
            embed.add_field(
                name=f"📤 {self.offerer.display_name} donne",
                value=f"**{offer_display}** ({self.offer_cat})",
                inline=True
            )
            
            embed.add_field(
                name=f"📥 {self.target.display_name} donne",
                value=f"**{return_display}** ({return_cat})",
                inline=True
            )
            
            embed.add_field(
                name="⚠️ Attention",
                value="Cet échange est **irréversible** !",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, view=final_view, ephemeral=True)
            
        except Exception as e:
            logging.error(f"[TRADE_RESPONSE] Erreur lors de la réponse: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de la réponse à l'échange.",
                ephemeral=True
            )


class TradeOfferCardModal(discord.ui.Modal, title="Proposer un échange"):
    """Modal pour proposer un échange de carte individuelle."""

    card_name = discord.ui.TextInput(
        label="Carte à échanger (nom ou identifiant)",
        placeholder="Ex : Alex (Variante) ou C42",
        required=True
    )

    def __init__(self, cog: "Cards", user: discord.User):
        super().__init__()
        self.cog = cog
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        """Traite la proposition d'échange."""
        await interaction.response.defer(ephemeral=True)

        try:
            input_text = self.card_name.value.strip()

            # Rechercher la carte dans l'inventaire de l'utilisateur
            card_match = self.cog.find_user_card_by_input(self.user.id, input_text)

            if not card_match:
                # Générer des suggestions
                suggestions = self.cog.get_user_card_suggestions(self.user.id, input_text)
                error_msg = f"❌ Carte non trouvée dans votre inventaire : **{input_text}**\n"
                error_msg += f"💡 Utilisez le nom exact de la carte ou son identifiant (ex: C42)"

                if suggestions:
                    error_msg += f"\n\n🔍 **Suggestions similaires :**\n"
                    for suggestion in suggestions:
                        error_msg += f"• {suggestion}\n"

                await interaction.followup.send(error_msg, ephemeral=True)
                return

            category, name = card_match

            # Créer l'embed de proposition
            display_name = name.removesuffix('.png')
            card_id = self.cog.get_card_identifier(category, name)
            display_text = f"{display_name} ({card_id})" if card_id else display_name

            embed = discord.Embed(
                title="🔄 Proposition d'échange",
                description=f"{self.user.display_name} propose d'échanger :",
                color=0x3498db
            )

            embed.add_field(
                name="Carte proposée",
                value=f"**{display_text}** ({category})",
                inline=False
            )

            embed.add_field(
                name="Instructions",
                value="Répondez avec le nom ou l'identifiant de la carte que vous souhaitez échanger.",
                inline=False
            )

            # Importer ici pour éviter les imports circulaires
            from .trade_views import TradeConfirmView

            # Pour l'instant, on crée une vue simple - dans une vraie implémentation,
            # il faudrait d'abord sélectionner l'utilisateur cible
            await interaction.followup.send(
                "✅ Proposition d'échange créée ! (Fonctionnalité en cours de développement)",
                embed=embed,
                ephemeral=True
            )

        except Exception as e:
            logging.error(f"[TRADE_OFFER] Erreur lors de la proposition: {e}")
            await interaction.followup.send(
                "❌ Une erreur est survenue lors de la proposition d'échange.",
                ephemeral=True
            )