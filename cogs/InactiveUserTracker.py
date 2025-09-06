import discord
from discord.ext import commands
import datetime
import asyncio
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class InactiveUserTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_role_id = 1018442041241374762
        self.category_ids = [
            1240553817393594439,
            1175022020749168662,
            1020820787583799358,
            1017797004019105842
        ]
        self.priority_channel_id = 1124836464904118482
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

        update_task = asyncio.create_task(self._update_status_periodically(status_message))

        try:
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

            await self._update_status(
                status_message,
                "En cours",
                f"Préparation de l'analyse pour {len(members_with_role)} membres avec le rôle {role.name}...",
                discord.Color.blue()
            )

            cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=limit_days)

            channels_to_check = await self._get_channels_to_check(ctx, status_message)

            (last_message_dates, channels_processed, messages_checked,
             total_channels, start_time) = await self._analyze_messages(
                ctx, channels_to_check, members_with_role, status_message, cutoff_date
            )

            await self._generate_report(
                ctx, role, members_with_role, last_message_dates, status_message,
                start_time, max_days, limit_days, channels_processed, total_channels, messages_checked
            )

        except Exception as e:
            await self._update_status(status_message, "Erreur", f"Une erreur s'est produite: {str(e)}", discord.Color.red())
            raise e
        finally:
            if not update_task.done():
                update_task.cancel()

    async def _get_channels_to_check(self, ctx, status_message):
        channels_to_check = []
        thread_ids_checked = set()

        priority_channel = ctx.guild.get_channel(self.priority_channel_id)
        if priority_channel:
            channels_to_check.append(priority_channel)

        for category_id in self.category_ids:
            category = ctx.guild.get_channel(category_id)
            if category and isinstance(category, discord.CategoryChannel):
                await self._update_status(status_message, "En cours", f"Listage des canaux de la catégorie {category.name}...", discord.Color.blue())

                for channel in category.channels:
                    if channel.id == self.priority_channel_id:
                        continue

                    if isinstance(channel, discord.TextChannel):
                        channels_to_check.append(channel)

                        try:
                            active_threads = await channel.active_threads()
                            for thread in active_threads:
                                if thread.id not in thread_ids_checked and thread.id != self.priority_channel_id:
                                    channels_to_check.append(thread)
                                    thread_ids_checked.add(thread.id)
                        except Exception as e:
                            logger.error(f"Erreur lors de la récupération des threads actifs dans {channel.name}: {e}")

                        try:
                            private_threads = await channel.archived_threads(limit=100, private=True)
                            for thread in private_threads:
                                if thread.id not in thread_ids_checked and thread.id != self.priority_channel_id:
                                    channels_to_check.append(thread)
                                    thread_ids_checked.add(thread.id)

                            public_threads = await channel.archived_threads(limit=100, private=False)
                            for thread in public_threads:
                                if thread.id not in thread_ids_checked and thread.id != self.priority_channel_id:
                                    channels_to_check.append(thread)
                                    thread_ids_checked.add(thread.id)
                        except Exception as e:
                            logger.error(f"Erreur lors de la récupération des threads archivés dans {channel.name}: {e}")

                    elif isinstance(channel, discord.ForumChannel):
                        channels_to_check.append(channel)

        try:
            await self._update_status(status_message, "En cours", "Récupération de tous les fils actifs du serveur...", discord.Color.blue())

            active_threads = ctx.guild.active_threads
            for thread in active_threads:
                if (thread.id not in thread_ids_checked and
                    thread.id != self.priority_channel_id and
                    (thread.parent and thread.parent.category_id in self.category_ids)):
                    channels_to_check.append(thread)
                    thread_ids_checked.add(thread.id)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des threads actifs du serveur: {e}")

        return channels_to_check

    async def _analyze_messages(self, ctx, channels_to_check, members_with_role, status_message, cutoff_date):
        last_message_dates = {}
        channels_processed = 0
        messages_checked = 0
        total_channels = len(channels_to_check)
        start_time = datetime.datetime.now()
        member_ids = [m.id for m in members_with_role]

        await self._update_status(
            status_message,
            "En cours",
            f"**Phase 1/2**: Analyse de {total_channels} canaux et fils dans les catégories spécifiées...",
            discord.Color.blue()
        )

        for i, channel in enumerate(channels_to_check):
            try:
                permissions_check = True
                try:
                    if hasattr(channel, "permissions_for") and not channel.permissions_for(ctx.guild.me).read_message_history:
                        permissions_check = False
                except Exception:
                    pass

                if not permissions_check:
                    continue

                try:
                    channel_name = getattr(channel, "name", f"Canal ID {channel.id}")
                    channel_type = "fil" if isinstance(channel, discord.Thread) else "salon"
                except Exception:
                    channel_name = f"Canal ID {channel.id}"
                    channel_type = "inconnu"

                channels_processed += 1
                percentage = (channels_processed / total_channels) * 100

                elapsed_time = (datetime.datetime.now() - start_time).total_seconds()
                minutes, seconds = divmod(int(elapsed_time), 60)

                progress_info = (
                    f"**Phase 1/2**: Analyse du {channel_type} **{channel_name}** ({i+1}/{total_channels})\n"
                    f"Progression: {percentage:.1f}% | Temps écoulé: {minutes}m {seconds}s\n"
                    f"Messages vérifiés: {messages_checked}"
                )

                await self._update_status(status_message, "En cours", progress_info, discord.Color.blue())

                try:
                    async for message in channel.history(limit=None, after=cutoff_date):
                        messages_checked += 1

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
                        if author_id in member_ids:
                            if author_id not in last_message_dates or message.created_at > last_message_dates[author_id]:
                                last_message_dates[author_id] = message.created_at
                except AttributeError:
                    continue
                except Exception as e:
                    logger.error(f"Erreur pendant la lecture de l'historique de {channel_name}: {e}")
                    continue

            except discord.errors.Forbidden:
                continue
            except Exception as e:
                logger.error(f"Erreur lors de l'analyse du canal {getattr(channel, 'name', str(channel.id))}: {e}")
                continue

        return last_message_dates, channels_processed, messages_checked, total_channels, start_time

    async def _generate_report(self, ctx, role, members_with_role, last_message_dates, status_message, start_time, max_days, limit_days, channels_processed, total_channels, messages_checked):
        await self._update_status(
            status_message,
            "Génération du rapport",
            f"**Phase 2/2**: Traitement des résultats pour {len(members_with_role)} membres...",
            discord.Color.gold()
        )

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

        inactive_members.sort(key=lambda x: x[1] if x[1] is not None else float('inf'), reverse=True)

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

        if inactive_members:
            for i, (member, days, last_date) in enumerate(inactive_members):
                embed = discord.Embed(
                    title=f"Membre inactif #{i+1}/{len(inactive_members)}",
                    color=discord.Color.orange(),
                )

                if member.avatar:
                    embed.set_thumbnail(url=member.avatar.url)

                embed.add_field(name="Membre", value=f"{member.mention} ({member.display_name})", inline=False)
                embed.add_field(name="ID", value=member.id, inline=True)

                if days is not None:
                    embed.add_field(name="Inactivité", value=f"{days} jours", inline=True)
                    last_date_str = last_date.strftime("%d/%m/%Y %H:%M")
                    embed.add_field(name="Dernier message", value=last_date_str, inline=True)
                else:
                    embed.add_field(name="Inactivité", value=f"Aucun message trouvé depuis au moins {limit_days} jours", inline=False)

                if member.joined_at:
                    join_date_str = member.joined_at.strftime("%d/%m/%Y")
                    embed.add_field(name="A rejoint le", value=join_date_str, inline=True)

                await ctx.send(embed=embed)
        else:
            await ctx.send(f"Aucun membre inactif trouvé avec le rôle {role.name}.")

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
                    pass
                else:
                    new_desc = embed.description.rstrip(".") + "." * dots
                    embed.description = new_desc
                    await message.edit(embed=embed)
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Erreur dans la mise à jour périodique: {e}")

async def setup(bot):
    await bot.add_cog(InactiveUserTracker(bot))
