import discord
from discord.ext import commands
import datetime
import asyncio
from typing import Dict, List, Optional
import logging

class InactiveUserTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_role_id = 1018442041241374762
        # IDs des catégories à vérifier
        self.category_ids = [
            1240553817393594439,
            1175022020749168662,
            1020820787583799358,
            1017797004019105842
        ]
        # ID du salon prioritaire
        self.priority_channel_id = 1124836464904118482
        # Pour éviter les recherches simultanées
        self.is_searching = False
    
    @commands.command(name='verifier_inactifs')
    @commands.has_permissions(administrator=True)
    async def check_inactive_users(self, ctx, max_days: Optional[int] = None, limit_days: Optional[int] = 180):
        """Vérifie les membres inactifs avec le rôle spécifié."""
        if self.is_searching:
            await ctx.send("Une recherche est déjà en cours. Veuillez attendre qu'elle se termine.")
            return
            
        self.is_searching = True
        try:
            await self._perform_inactive_search(ctx, max_days, limit_days)
        finally:
            self.is_searching = False
    
    async def _perform_inactive_search(self, ctx, max_days: Optional[int] = None, limit_days: Optional[int] = 180):
        embed = discord.Embed(
            title="Recherche d'inactivité",
            description="Initialisation de la recherche...",
            color=discord.Color.blue()
        )
        status_message = await ctx.send(embed=embed)
        
        # Mise à jour régulière du message de statut
        update_task = asyncio.create_task(self._update_status_periodically(status_message))
        
        try:
            # Récupérer le rôle cible
            role = ctx.guild.get_role(self.target_role_id)
            if not role:
                await self._update_status(status_message, "Erreur", f"Le rôle avec l'ID {self.target_role_id} n'a pas été trouvé.", discord.Color.red())
                update_task.cancel()
                return
            
            members_with_role = [member for member in ctx.guild.members if role in member.roles]
            if not members_with_role:
                await self._update_status(status_message, "Terminé", f"Aucun membre n'a le rôle {role.name}.", discord.Color.green())
                update_task.cancel()
                return
            
            await self._update_status(status_message, "En cours", 
                f"Préparation de l'analyse pour {len(members_with_role)} membres avec le rôle {role.name}...", discord.Color.blue())
            
            # Dictionnaire pour stocker le dernier message de chaque membre
            last_message_dates = {}
            
            # Calculer la date limite de recherche
            cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=limit_days)
            
            # Obtenir tous les canaux textuels à vérifier
            channels_to_check = []
            thread_ids_checked = set()  # Pour éviter les doublons
            
            # D'abord ajouter le canal prioritaire s'il existe
            priority_channel = ctx.guild.get_channel(self.priority_channel_id)
            if priority_channel:
                channels_to_check.append(priority_channel)
            
            # Ensuite, ajouter tous les autres canaux des catégories spécifiées
            for category_id in self.category_ids:
                category = ctx.guild.get_channel(category_id)
                if category and isinstance(category, discord.CategoryChannel):
                    await self._update_status(status_message, "En cours", 
                        f"Listage des canaux de la catégorie {category.name}...", discord.Color.blue())
                    
                    for channel in category.channels:
                        if channel.id == self.priority_channel_id:
                            continue  # Déjà ajouté
                            
                        # Ajouter les canaux textuels
                        if isinstance(channel, discord.TextChannel):
                            channels_to_check.append(channel)
                            
                            # Récupérer les threads actifs
                            try:
                                active_threads = await channel.active_threads()
                                for thread in active_threads:
                                    if thread.id not in thread_ids_checked and thread.id != self.priority_channel_id:
                                        channels_to_check.append(thread)
                                        thread_ids_checked.add(thread.id)
                            except Exception as e:
                                print(f"Erreur lors de la récupération des threads actifs dans {channel.name}: {e}")
                            
                            # Récupérer les threads archivés
                            try:
                                # Utiliser la méthode de récupération d'archives privées
                                private_threads = await channel.archived_threads(limit=100, private=True)
                                for thread in private_threads:
                                    if thread.id not in thread_ids_checked and thread.id != self.priority_channel_id:
                                        channels_to_check.append(thread)
                                        thread_ids_checked.add(thread.id)
                                
                                # Utiliser la méthode de récupération d'archives publiques
                                public_threads = await channel.archived_threads(limit=100, private=False)
                                for thread in public_threads:
                                    if thread.id not in thread_ids_checked and thread.id != self.priority_channel_id:
                                        channels_to_check.append(thread)
                                        thread_ids_checked.add(thread.id)
                            except Exception as e:
                                print(f"Erreur lors de la récupération des threads archivés dans {channel.name}: {e}")
                        
                        # Pour les forums, récupérer leurs threads
                        elif isinstance(channel, discord.ForumChannel):
                            # On peut seulement parcourir les posts du forum directement
                            channels_to_check.append(channel)
            
            # Récupérer les fils actifs du serveur (méthode alternative)
            try:
                await self._update_status(status_message, "En cours", 
                    "Récupération de tous les fils actifs du serveur...", discord.Color.blue())
                    
                active_threads = ctx.guild.active_threads
                for thread in active_threads:
                    if (thread.id not in thread_ids_checked and 
                        thread.id != self.priority_channel_id and 
                        (thread.parent and thread.parent.category_id in self.category_ids)):
                        channels_to_check.append(thread)
                        thread_ids_checked.add(thread.id)
            except Exception as e:
                print(f"Erreur lors de la récupération des threads actifs du serveur: {e}")
            
            total_channels = len(channels_to_check)
            await self._update_status(status_message, "En cours", 
                f"**Phase 1/2**: Analyse de {total_channels} canaux et fils dans les catégories spécifiées...", discord.Color.blue())
            
            # Compteurs pour les statistiques
            channels_processed = 0
            messages_checked = 0
            start_time = datetime.datetime.now()
            
            # Parcourir tous les canaux à vérifier
            for i, channel in enumerate(channels_to_check):
                try:
                    # Vérifier les permissions si possible
                    permissions_check = True
                    try:
                        if hasattr(channel, "permissions_for") and not channel.permissions_for(ctx.guild.me).read_message_history:
                            permissions_check = False
                    except Exception as e:
                        logging.warning(f"[INACTIVE] Permission check failed for channel {getattr(channel, 'id', 'unknown')}: {e}")
                        
                    if not permissions_check:
                        continue
                    
                    # Déterminer le nom et le type du canal
                    try:
                        channel_name = getattr(channel, "name", f"Canal ID {channel.id}")
                        channel_type = "fil" if isinstance(channel, discord.Thread) else "salon"
                    except Exception as e:
                        logging.warning(f"[INACTIVE] Unable to determine channel info for {getattr(channel, 'id', 'unknown')}: {e}")
                        channel_name = f"Canal ID {channel.id}"
                        channel_type = "inconnu"
                    
                    # Calcul du pourcentage de progression
                    channels_processed += 1
                    percentage = (channels_processed / total_channels) * 100
                    
                    # Mise à jour du statut avec plus d'informations
                    elapsed_time = (datetime.datetime.now() - start_time).total_seconds()
                    minutes, seconds = divmod(int(elapsed_time), 60)
                    
                    progress_info = (
                        f"**Phase 1/2**: Analyse du {channel_type} **{channel_name}** ({i+1}/{total_channels})\n"
                        f"Progression: {percentage:.1f}% | Temps écoulé: {minutes}m {seconds}s\n"
                        f"Messages vérifiés: {messages_checked}"
                    )
                    
                    await self._update_status(status_message, "En cours", progress_info, discord.Color.blue())
                    
                    # Parcourir l'historique des messages jusqu'à la date limite
                    try:
                        async for message in channel.history(limit=None, after=cutoff_date):
                            messages_checked += 1
                            
                            # Mise à jour périodique du compteur de messages
                            if messages_checked % 500 == 0:
                                elapsed_time = (datetime.datetime.now() - start_time).total_seconds()
                                minutes, seconds = divmod(int(elapsed_time), 60)
                                
                                progress_info = (
                                    f"**Phase 1/2**: Analyse du {channel_type} **{channel_name}** ({i+1}/{total_channels})\n"
                                    f"Progression: {percentage:.1f}% | Temps écoulé: {minutes}m {seconds}s\n"
                                    f"Messages vérifiés: {messages_checked}"
                                )
                                await self._update_status(status_message, "En cours", progress_info, discord.Color.blue())
                            
                            author_id = message.author.id
                            # Vérifier si l'auteur a le rôle cible
                            if author_id in [member.id for member in members_with_role]:
                                # Stocker la date la plus récente
                                if author_id not in last_message_dates or message.created_at > last_message_dates[author_id]:
                                    last_message_dates[author_id] = message.created_at
                    except AttributeError:
                        # Certains types de canaux pourraient ne pas avoir de méthode history()
                        continue
                    except Exception as e:
                        print(f"Erreur pendant la lecture de l'historique de {channel_name}: {e}")
                        continue
                    
                except discord.errors.Forbidden:
                    continue
                except Exception as e:
                    error_msg = f"Erreur lors de l'analyse du canal {getattr(channel, 'name', str(channel.id))}: {e}"
                    print(error_msg)
                    continue
            
            # Génération du rapport
            await self._update_status(status_message, "Génération du rapport", 
                                     f"**Phase 2/2**: Traitement des résultats pour {len(members_with_role)} membres...", 
                                     discord.Color.gold())
            
            now = datetime.datetime.now(datetime.timezone.utc)
            inactive_members = []
            
            for member in members_with_role:
                if member.id in last_message_dates:
                    last_date = last_message_dates[member.id]
                    days_inactive = (now - last_date).days
                    if max_days is None or days_inactive >= max_days:
                        inactive_members.append((member, days_inactive, last_date))
                else:
                    inactive_members.append((member, None, None))
            
            # Trier les membres par inactivité (du plus inactif au moins inactif)
            # Les membres sans date trouvée apparaissent en premier
            inactive_members.sort(key=lambda x: x[1] if x[1] is not None else float('inf'), reverse=True)
            
            # Terminer la mise à jour périodique du statut
            update_task.cancel()
            
            # Statistiques finales
            elapsed_time = (datetime.datetime.now() - start_time).total_seconds()
            minutes, seconds = divmod(int(elapsed_time), 60)
            
            stats = (
                f"**Recherche terminée en {minutes}m {seconds}s**\n"
                f"Canaux analysés: {channels_processed}/{total_channels}\n"
                f"Messages vérifiés: {messages_checked}\n"
                f"Membres avec activité trouvée: {len(last_message_dates)}/{len(members_with_role)}\n"
                f"Membres inactifs listés: {len(inactive_members)}"
            )
            
            await self._update_status(status_message, "Terminé", stats, discord.Color.green())
            
            # Envoyer le rapport avec un format plus élégant
            if inactive_members:
                # Créer des embeds pour chaque membre inactif
                for i, (member, days, last_date) in enumerate(inactive_members):
                    embed = discord.Embed(
                        title=f"Membre inactif #{i+1}/{len(inactive_members)}",
                        color=discord.Color.orange()
                    )
                    
                    # Ajouter l'avatar du membre si disponible
                    if member.avatar:
                        embed.set_thumbnail(url=member.avatar.url)
                    
                    # Ajouter les informations du membre
                    embed.add_field(name="Membre", value=f"{member.mention} ({member.display_name})", inline=False)
                    embed.add_field(name="ID", value=member.id, inline=True)
                    
                    # Ajouter les informations d'inactivité
                    if days is not None:
                        embed.add_field(name="Inactivité", value=f"{days} jours", inline=True)
                        last_date_str = last_date.strftime("%d/%m/%Y %H:%M")
                        embed.add_field(name="Dernier message", value=last_date_str, inline=True)
                    else:
                        embed.add_field(name="Inactivité", value=f"Aucun message trouvé depuis au moins {limit_days} jours", inline=False)
                    
                    # Ajouter la date d'arrivée sur le serveur si disponible
                    if member.joined_at:
                        join_date_str = member.joined_at.strftime("%d/%m/%Y")
                        embed.add_field(name="A rejoint le", value=join_date_str, inline=True)
                    
                    await ctx.send(embed=embed)
            else:
                await ctx.send(f"Aucun membre inactif trouvé avec le rôle {role.name}.")
                
        except Exception as e:
            await self._update_status(status_message, "Erreur", f"Une erreur s'est produite: {str(e)}", discord.Color.red())
            raise e
        finally:
            # S'assurer que la tâche d'update est annulée
            if not update_task.done():
                update_task.cancel()
    
    async def _update_status(self, message, title, description, color):
        """Met à jour le message de statut avec un nouvel embed."""
        embed = discord.Embed(
            title=f"Recherche d'inactivité: {title}",
            description=description,
            color=color,
            timestamp=datetime.datetime.now()
        )
        await message.edit(embed=embed)
    
    async def _update_status_periodically(self, message):
        """Met à jour périodiquement le message de statut pour montrer que le bot est toujours actif."""
        dots = 0
        try:
            while True:
                dots = (dots % 3) + 1
                embed = message.embeds[0]
                if not embed.description.endswith("..."):
                    # Ne modifie pas si la description a changé entre-temps
                    pass
                else:
                    new_desc = embed.description.rstrip(".") + "." * dots
                    embed.description = new_desc
                    await message.edit(embed=embed)
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            # Tâche annulée normalement
            pass
        except Exception as e:
            print(f"Erreur dans la mise à jour périodique: {e}")

async def setup(bot):
    await bot.add_cog(InactiveUserTracker(bot))