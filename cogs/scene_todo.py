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
        self.actions_input = discord.ui.TextInput(
            label="Actions initiales",
            placeholder="Une action par ligne",
            required=False,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.mj_input)
        self.add_item(self.name)
        self.add_item(self.actions_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        actions = [a.strip() for a in self.actions_input.value.splitlines() if a.strip()]
        scene = self.cog.add_scene(self.mj_input.value.strip(), self.name.value, actions)

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


class ActionButton(discord.ui.Button):
    def __init__(self, cog, scene_id: int, action_id: int, label: str, done: bool):
        style = discord.ButtonStyle.secondary if not done else discord.ButtonStyle.success
        super().__init__(label=label, style=style, custom_id=f"action_{scene_id}_{action_id}", disabled=done)
        self.cog = cog
        self.scene_id = scene_id
        self.action_id = action_id

    async def callback(self, interaction: discord.Interaction):
        if not any(r.id == MJ_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("Permission refusée.", ephemeral=True)
            return
        action = self.cog.toggle_action(self.scene_id, self.action_id)
        if action:
            await interaction.response.send_message(f"Action '{action['label']}' mise à jour.", ephemeral=True)
            self.cog.track_message(interaction.message)
            await self.cog.refresh_message(interaction.message)


class DeleteSceneButton(discord.ui.Button):
    def __init__(self, cog, scene_id: int, name: str):
        super().__init__(label=f"✖ {name}", style=discord.ButtonStyle.danger, custom_id=f"delete_{scene_id}")
        self.cog = cog
        self.scene_id = scene_id

    async def callback(self, interaction: discord.Interaction):
        if not any(r.id == MJ_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("Permission refusée.", ephemeral=True)
            return
        scene = self.cog.delete_scene(self.scene_id)
        if scene:
            await interaction.response.send_message(f"Scène '{scene['name']}' supprimée.", ephemeral=True)
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
            self.add_item(DeleteSceneButton(cog, scene['id'], scene['name']))
            for action in scene.get("actions", []):
                self.add_item(ActionButton(cog, scene['id'], action['id'], action['label'], action.get('done', False)))

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
                    data = {"scenes": data, "message": None}
                scenes = data.get("scenes", [])
                # migration: ensure actions key exists
                for s in scenes:
                    s.setdefault("actions", [])
                    for a in s["actions"]:
                        a.setdefault("done", False)
                data["scenes"] = scenes
                return data
        return {"scenes": [], "message": None}

    def save_data(self):
        with open(SCENES_FILE, 'w', encoding='utf-8') as f:
            json.dump({"scenes": self.scenes, "message": self.message_info}, f, ensure_ascii=False, indent=2)

    # --------- Scene Operations ---------
    def add_scene(self, mj_name: str, name: str, actions=None):
        scene_id = max([s['id'] for s in self.scenes], default=0) + 1
        scene = {
            "id": scene_id,
            "name": name,
            "mj": mj_name,
            "created_at": datetime.utcnow().isoformat(),
            "completed": False,
            "actions": [],
        }
        if actions:
            for idx, label in enumerate(actions, start=1):
                scene["actions"].append({"id": idx, "label": label, "done": False})
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

    def add_action(self, scene_id: int, label: str):
        scene = self.get_scene(scene_id)
        if not scene:
            return None
        actions = scene.setdefault("actions", [])
        action_id = max([a["id"] for a in actions], default=0) + 1
        action = {"id": action_id, "label": label, "done": False}
        actions.append(action)
        self.save_data()
        return action

    def toggle_action(self, scene_id: int, action_id: int):
        scene = self.get_scene(scene_id)
        if not scene:
            return None
        for action in scene.get("actions", []):
            if action["id"] == action_id:
                action["done"] = not action.get("done", False)
                self.save_data()
                return action
        return None

    def delete_scene(self, scene_id: int):
        scene = self.get_scene(scene_id)
        if not scene:
            return None
        self.scenes = [s for s in self.scenes if s["id"] != scene_id]
        self.save_data()
        return scene

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
            actions_lines = []
            for action in scene.get("actions", []):
                check = "✅" if action.get("done") else "⬜️"
                actions_lines.append(f"{check} {action['label']}")
            actions_text = "\n".join(actions_lines)
            value = f"MJ : {mj_name}\nDepuis {since}"
            if actions_lines:
                value += "\n" + actions_text
            embed.add_field(name=scene["name"], value=value, inline=False)
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
