import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime
import json
import os

SCENES_FILE = "scenes.json"

MJ_ROLE_ID = 1018179623886000278

class AddSceneModal(discord.ui.Modal, title="Nouvelle scène"):
    def __init__(self, cog, guild: discord.Guild):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.mj_input = discord.ui.TextInput(
            label="MJ responsable",
            placeholder="Nom du MJ",
            required=True,
        )
        self.name = discord.ui.TextInput(label="Nom de la scène", required=True)
        self.add_item(self.mj_input)
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        scene = self.cog.add_scene(self.mj_input.value.strip(), self.name.value)
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
        if not any(r.id == MJ_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("Permission refusée.", ephemeral=True)
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
        data = self.load_data()
        self.scenes = data.get("scenes", [])
        self.message_info = data.get("message")
        self.update_loop.start()

    def cog_unload(self):
        self.update_loop.cancel()

    def track_message(self, message: discord.Message):
        self.message_info = {"channel_id": message.channel.id, "message_id": message.id}
        self.save_data()

    @tasks.loop(hours=1)
    async def update_loop(self):
        if not self.message_info:
            return
        channel = self.bot.get_channel(self.message_info["channel_id"])
        if channel:
            try:
                message = await channel.fetch_message(self.message_info["message_id"])
                await self.refresh_message(message)
            except discord.NotFound:
                self.message_info = None
                self.save_data()

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()

    # --------- Persistence ---------
    def load_data(self):
        if os.path.isfile(SCENES_FILE):
            with open(SCENES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {"scenes": data, "message": None}
                return data
        return {"scenes": [], "message": None}

    def save_data(self):
        with open(SCENES_FILE, 'w', encoding='utf-8') as f:
            json.dump({"scenes": self.scenes, "message": self.message_info}, f, ensure_ascii=False, indent=2)

    # --------- Scene Operations ---------
    def add_scene(self, mj_name: str, name: str):
        scene_id = max([s['id'] for s in self.scenes], default=0) + 1
        scene = {
            "id": scene_id,
            "name": name,
            "mj": mj_name,
            "created_at": datetime.utcnow().isoformat(),
            "completed": False,
        }
        self.scenes.append(scene)
        self.save_data()
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
            self.save_data()
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
            since = self.format_time_ago(scene["created_at"])
            mj_name = scene.get("mj", "?")
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
            mj_name = scene.get("mj", "?")
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
