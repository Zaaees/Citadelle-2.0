import discord
from discord.ext import commands
import datetime
import asyncio
from typing import Dict, List, Optional

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
    
    @commands.command(name='verifier_inactifs')
    @commands.has_permissions(administrator=True)
    async def check_inactive_users(self, ctx, max_days: Optional[int] = None, limit_days: Optional[int] = 365):
        """Vérifie les membres inactifs avec le rôle spécifié.
        
        Args:
            max_days: Nombre de jours minimum d'inactivité pour apparaître dans la liste
            limit_days: Nombre de jours maximum d'historique à parcourir (par défaut: 365)
        """
        await ctx.send("Vérification des membres inactifs en cours... Cela peut prendre un temps considérable.")
        
        # Récupérer le rôle cible
        role = ctx.guild.get_role(self.target_role_id)
        if not role:
            await ctx.send(f"Erreur: Le rôle avec l'ID {self.target_role_id} n'a pas été trouvé.")
            return
        
        members_with_role = [member for member in ctx.guild.members if role in member.roles]
        if not members_with_role:
            await ctx.send(f"Aucun membre n'a le rôle {role.name}.")
            return
        
        status_message = await ctx.send(f"Analyse de l'activité de {len(members_with_role)} membres avec le rôle {role.name}...")
        
        # Dictionnaire pour stocker le dernier message de chaque membre
        last_message_dates = {}
        # Dictionnaire pour suivre quels membres ont été trouvés
        members_found = {member.id: False for member in members_with_role}
        
        # Calculer la date limite de recherche
        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=limit_days)
        
        # Obtenir tous les canaux textuels à vérifier
        channels_to_check = []
        
        # D'abord ajouter le canal prioritaire s'il existe
        priority_channel = ctx.guild.get_channel(self.priority_channel_id)
        if priority_channel:
            channels_to_check.append(priority_channel)
        
        # Ensuite, ajouter tous les autres canaux des catégories spécifiées
        for category_id in self.category_ids:
            category = ctx.guild.get_channel(category_id)
            if category and isinstance(category, discord.CategoryChannel):
                for channel in category.channels:
                    # Vérifier si c'est un canal textuel, fil ou forum
                    if isinstance(channel, (discord.TextChannel, discord.Thread)) and channel.id != self.priority_channel_id:
                        channels_to_check.append(channel)
        
                    # Si c'est un forum, ajouter tous ses fils actifs
                    if isinstance(channel, discord.ForumChannel):
                        threads = await channel.active_threads()
                        for thread in threads:
                            if thread.id != self.priority_channel_id:
                                channels_to_check.append(thread)
        
        # Vérifier également les fils actifs dans les canaux textuels
        for channel in ctx.guild.text_channels:
            if isinstance(channel, discord.TextChannel) and channel.category_id in self.category_ids:
                threads = await channel.archived_threads(limit=100)
                for thread in threads:
                    if thread.id != self.priority_channel_id:
                        channels_to_check.append(thread)
        
        total_channels = len(channels_to_check)
        await status_message.edit(content=f"Analyse de {total_channels} canaux dans les catégories spécifiées...")
        
        # Parcourir tous les canaux à vérifier
        for i, channel in enumerate(channels_to_check):
            try:
                # Vérifier les permissions
                if hasattr(channel, "permissions_for") and not channel.permissions_for(ctx.guild.me).read_message_history:
                    continue
                
                channel_name = getattr(channel, "name", f"Canal ID {channel.id}")
                await status_message.edit(content=f"Analyse du canal {channel_name} ({i+1}/{total_channels})...")
                
                # Parcourir l'historique des messages jusqu'à la date limite
                try:
                    async for message in channel.history(limit=None, after=cutoff_date):
                        author_id = message.author.id
                        if author_id in members_found and not members_found[author_id]:
                            if author_id not in last_message_dates or message.created_at > last_message_dates[author_id]:
                                last_message_dates[author_id] = message.created_at
                                members_found[author_id] = True
                except AttributeError:
                    # Certains types de canaux pourraient ne pas avoir de méthode history()
                    continue
                
                # Si tous les membres ont été trouvés, on peut arrêter la recherche
                if all(members_found.values()):
                    await status_message.edit(content="Tous les membres ont été trouvés, génération du rapport...")
                    break
                
            except discord.errors.Forbidden:
                continue
            except Exception as e:
                await ctx.send(f"Erreur lors de l'analyse du canal {getattr(channel, 'name', channel.id)}: {e}")
                continue
        
        # Génération du rapport
        now = datetime.datetime.now(datetime.timezone.utc)
        inactive_members = []
        
        for member in members_with_role:
            if member.id in last_message_dates:
                last_date = last_message_dates[member.id]
                days_inactive = (now - last_date).days
                if max_days is None or days_inactive >= max_days:
                    inactive_members.append((member, days_inactive, last_date))
            else:
                inactive_members.append((member, limit_days, None))
        
        # Trier les membres par inactivité (du plus inactif au moins inactif)
        inactive_members.sort(key=lambda x: x[1], reverse=True)
        
        # Générer le rapport
        report = []
        for member, days, last_date in inactive_members:
            if last_date is None:
                report.append(f"{member.display_name} ({member.id}): Aucun message trouvé depuis au moins {limit_days} jours")
            else:
                last_date_str = last_date.strftime("%d/%m/%Y %H:%M")
                report.append(f"{member.display_name} ({member.id}): {days} jours d'inactivité (dernier message le {last_date_str})")
        
        # Envoyer le rapport
        if report:
            chunks = self.split_text(report)
            for i, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title=f"Membres inactifs avec le rôle {role.name} ({i+1}/{len(chunks)})",
                    description=chunk,
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
        else:
            await ctx.send(f"Aucun membre inactif trouvé avec le rôle {role.name}.")
    
    def split_text(self, lines: List[str]) -> List[str]:
        """Découpe une liste de lignes en chunks de 1900 caractères max."""
        chunks = []
        current_chunk = ""
        
        for line in lines:
            if len(current_chunk) + len(line) + 1 > 1900:  # +1 pour le \n
                chunks.append(current_chunk)
                current_chunk = line
            else:
                if current_chunk:
                    current_chunk += "\n" + line
                else:
                    current_chunk = line
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

async def setup(bot):
    await bot.add_cog(InactiveUserTracker(bot))