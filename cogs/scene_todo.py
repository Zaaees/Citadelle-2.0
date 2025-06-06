import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime
import re
import json
import os

SCENES_FILE = "scenes.json"

class AddSceneModal(discord.ui.Modal, title="Nouvelle scène"):
    def __init__(self, cog, guild: discord.Guild):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.mj_input = discord.ui.TextInput(
            label="MJ responsable",
            placeholder="Mention ou nom",
            required=True,
        )
        self.name = discord.ui.TextInput(label="Nom de la scène", required=True)
        self.add_item(self.mj_input)
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        mj_text = self.mj_input.value.strip()
        mj_id = None

        match = re.match(r"<@!?(\d+)>", mj_text)
        if match:
            mj_id = int(match.group(1))
        else:
            member = discord.utils.find(
                lambda m: m.display_name.lower() == mj_text.lower()
                or m.name.lower() == mj_text.lower(),
                self.guild.members,
            )
            if member:
                mj_id = member.id

        if not mj_id:
            await interaction.response.send_message(
                "MJ introuvable.", ephemeral=True
            )
            return

        scene = self.cog.add_scene(mj_id, self.name.value)
        await interaction.response.send_message(
            f"Scène '{scene['name']}' ajoutée.", ephemeral=True
        )
        self.cog.track_message(interaction.message)
        await self.cog.refresh_message(interaction.message)

class CompleteSceneButton(discord.ui.Button):
    def __init__(self, cog, scene_id: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.success, custom_id=f"complete_{scene_id}")
        self.cog = cog
        self.scene_id = scene_id

    async def callback(self, interaction: discord.Interaction):
        scene = self.cog.get_scene(self.scene_id)
        if not scene:
            await interaction.response.send_message("Scène inconnue.", ephemeral=True)
            return
        if scene["mj_id"] != interaction.user.id:
            await interaction.response.send_message("Seul le MJ assigné peut terminer cette scène.", ephemeral=True)
            return
        self.cog.complete_scene(self.scene_id)
        await interaction.response.send_message(f"Scène '{scene['name']}' terminée.", ephemeral=True)
        await self.cog.announce_completion(interaction.guild, scene)
        self.cog.track_message(interaction.message)
        await self.cog.refresh_message(interaction.message)

class ScenesView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(AddSceneButton(cog))
        for scene in cog.get_active_scenes():
            label = f"✔ {scene['name']}"
            self.add_item(CompleteSceneButton(cog, scene['id'], label))

class AddSceneButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(label="Ajouter une scène", style=discord.ButtonStyle.primary, custom_id="add_scene")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        modal = AddSceneModal(self.cog, interaction.guild)
        await interaction.response.send_modal(modal)

class SceneTodo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scenes = self.load_scenes()
        self.tracked_messages = []
        self.update_loop.start()

    def cog_unload(self):
        self.update_loop.cancel()

    def track_message(self, message: discord.Message):
        info = (message.channel.id, message.id)
        if info not in self.tracked_messages:
            self.tracked_messages.append(info)

    @tasks.loop(hours=1)
    async def update_loop(self):
        for channel_id, message_id in self.tracked_messages.copy():
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    await self.refresh_message(message)
                except discord.NotFound:
                    self.tracked_messages.remove((channel_id, message_id))

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()

    # --------- Persistence ---------
    def load_scenes(self):
        if os.path.isfile(SCENES_FILE):
            with open(SCENES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def save_scenes(self):
        with open(SCENES_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.scenes, f, ensure_ascii=False, indent=2)

    # --------- Scene Operations ---------
    def add_scene(self, mj_id: int, name: str):
        scene_id = max([s['id'] for s in self.scenes], default=0) + 1
        scene = {
            "id": scene_id,
            "name": name,
            "mj_id": mj_id,
            "created_at": datetime.utcnow().isoformat(),
            "completed": False,
        }
        self.scenes.append(scene)
        self.save_scenes()
        return scene

    def get_scene(self, scene_id: int):
        for s in self.scenes:
            if s["id"] == scene_id:
                return s
        return None

    def complete_scene(self, scene_id: int):
        scene = self.get_scene(scene_id)
        if scene and not scene.get("completed"):
            scene["completed"] = True
            self.save_scenes()
        return scene

    def get_active_scenes(self):
        return [s for s in self.scenes if not s.get("completed")]

    # --------- Helper ---------
    def format_time_ago(self, iso_time: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_time)
        except Exception:
            return "?"
        diff = datetime.utcnow() - dt
        total_hours = diff.days * 24 + diff.seconds // 3600
        days, hours = divmod(total_hours, 24)
        parts = []
        if days:
            parts.append(f"{days} jour{'s' if days > 1 else ''}")
        if hours or not parts:
            parts.append(f"{hours} heure{'s' if hours > 1 else ''}")
        return " et ".join(parts)

    def build_embed(self):
        embed = discord.Embed(title="Scènes en cours", color=discord.Color.blurple())
        scenes = self.get_active_scenes()
        if not scenes:
            embed.description = "Aucune scène en cours."
            return embed
        for scene in scenes:
            mj = self.bot.get_user(scene["mj_id"])
            mj_name = mj.mention if mj else f"<@{scene['mj_id']}>"
            since = self.format_time_ago(scene["created_at"])
            embed.add_field(name=scene["name"], value=f"MJ : {mj_name}\nDepuis {since}", inline=False)
        return embed

    async def refresh_message(self, message: discord.Message):
        try:
            await message.edit(embed=self.build_embed(), view=ScenesView(self))
        except discord.NotFound:
            pass

    async def announce_completion(self, guild: discord.Guild, scene: dict):
        channel_id = int(os.getenv("SCENE_TODO_CHANNEL_ID", 0))
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            mj = guild.get_member(scene["mj_id"])
            mj_name = mj.mention if mj else f"<@{scene['mj_id']}>"
            await channel.send(f"✅ La scène **{scene['name']}** menée par {mj_name} est terminée.")

    # --------- Commands ---------
    @app_commands.command(name="scenes", description="Gérer la to-do list des scènes")
    async def scenes_cmd(self, interaction: discord.Interaction):
        embed = self.build_embed()
        view = ScenesView(self)
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        self.track_message(msg)

async def setup(bot: commands.Bot):
    await bot.add_cog(SceneTodo(bot))
    print("Cog scene_todo chargé avec succès")
