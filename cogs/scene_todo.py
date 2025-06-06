import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import json
import os

SCENES_FILE = "scenes.json"

class AddSceneModal(discord.ui.Modal, title="Nouvelle scène"):
    def __init__(self, cog, mj: discord.Member):
        super().__init__()
        self.cog = cog
        self.mj = mj
        self.name = discord.ui.TextInput(label="Nom de la scène", required=True)
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        scene = self.cog.add_scene(self.mj.id, self.name.value)
        await interaction.response.send_message(f"Scène '{scene['name']}' ajoutée.", ephemeral=True)
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
        modal = AddSceneModal(self.cog, interaction.user)
        await interaction.response.send_modal(modal)

class SceneTodo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scenes = self.load_scenes()

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
        hours, remainder = divmod(int(diff.total_seconds()), 3600)
        days, hours = divmod(hours, 24)
        if days:
            return f"il y a {days}j {hours}h"
        return f"il y a {hours}h {remainder//60}m"

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

async def setup(bot: commands.Bot):
    await bot.add_cog(SceneTodo(bot))
    print("Cog scene_todo chargé avec succès")
