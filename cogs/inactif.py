import discord
from discord.ext import commands
import datetime
import asyncio
from typing import Dict, List, Optional

class inactif(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_role_id = 1018442041241374762
    
    @commands.command(name='verifier_inactifs')
    @commands.has_permissions(administrator=True)
    async def check_inactive_users(self, ctx, max_days: Optional[int] = None):
        """Vérifie les membres inactifs avec le rôle spécifié.
        
        Args:
            max_days: Nombre de jours optionnel pour filtrer les membres inactifs depuis plus longtemps
        """
        await ctx.send("Vérification des membres inactifs en cours... Cela peut prendre du temps.")
        
        # Récupérer le rôle cible
        role = ctx.guild.get_role(self.target_role_id)
        if not role:
            await ctx.send(f"Erreur: Le rôle avec l'ID {self.target_role_id} n'a pas été trouvé.")
            return
        
        members_with_role = [member for member in ctx.guild.members if role in member.roles]
        if not members_with_role:
            await ctx.send(f"Aucun membre n'a le rôle {role.name}.")
            return
        
        await ctx.send(f"Analyse de l'activité de {len(members_with_role)} membres avec le rôle {role.name}...")
        
        # Stocker les informations d'inactivité
        inactive_members = []
        progress_message = await ctx.send("Progression: 0%")
        
        for i, member in enumerate(members_with_role):
            # Mettre à jour la progression toutes les 5 membres
            if i % 5 == 0:
                progress = (i / len(members_with_role)) * 100
                await progress_message.edit(content=f"Progression: {progress:.1f}%")
            
            last_message_date = await self.find_last_message(ctx.guild, member)
            if last_message_date:
                days_inactive = (datetime.datetime.now(datetime.timezone.utc) - last_message_date).days
                if max_days is None or days_inactive >= max_days:
                    inactive_members.append((member, days_inactive, last_message_date))
            else:
                # Si aucun message trouvé, considérer comme jamais actif
                inactive_members.append((member, float('inf'), None))
        
        await progress_message.edit(content="Progression: 100%")
        
        # Trier les membres par inactivité (du plus inactif au moins inactif)
        inactive_members.sort(key=lambda x: x[1], reverse=True)
        
        # Générer le rapport
        report = []
        for member, days, last_date in inactive_members:
            if days == float('inf'):
                report.append(f"{member.display_name} ({member.id}): Aucun message trouvé")
            else:
                last_date_str = last_date.strftime("%d/%m/%Y %H:%M")
                report.append(f"{member.display_name} ({member.id}): {days} jours d'inactivité (dernier message le {last_date_str})")
        
        # Envoyer le rapport
        if report:
            # Découper le rapport en morceaux de 1900 caractères pour respecter les limites Discord
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
    
    async def find_last_message(self, guild: discord.Guild, member: discord.Member) -> Optional[datetime.datetime]:
        """Trouve la date du dernier message d'un membre dans le serveur."""
        last_message_date = None
        
        for channel in guild.text_channels:
            try:
                # Vérifier si le bot a la permission de lire l'historique
                if not channel.permissions_for(guild.me).read_message_history:
                    continue
                
                # Chercher le dernier message du membre dans ce canal
                async for message in channel.history(limit=None, user=member):
                    if last_message_date is None or message.created_at > last_message_date:
                        last_message_date = message.created_at
                    # Si on trouve un message, pas besoin de continuer à chercher dans ce canal
                    break
            except discord.errors.Forbidden:
                # Ignorer les canaux où le bot n'a pas la permission
                continue
            except Exception as e:
                print(f"Erreur lors de la recherche dans {channel.name}: {e}")
                continue
        
        return last_message_date
    
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
    await bot.add_cog(inactif(bot))