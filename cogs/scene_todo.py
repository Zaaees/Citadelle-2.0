import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import json
import os

SCENE_CHANNEL_ID = 1380704586016362626
LOG_CHANNEL_ID = 1097883902279946360
MJ_ROLE_ID = 1018179623886000278
SCENES_FILE = "scenes.json"
EMBED_COLOR = 0x6d5380


class AddSceneModal(discord.ui.Modal, title="Créer une scène"):
    def __init__(self, cog: "SceneTodo"):
        super().__init__()
        self.cog = cog
        self.mj_input = discord.ui.TextInput(label="MJ responsable", required=True)
        self.name_input = discord.ui.TextInput(label="Nom de la scène", required=True)
        self.actions_input = discord.ui.TextInput(
            label="Actions initiales (une par ligne)",
            style=discord.TextStyle.paragraph,
            required=False,
        )
        self.add_item(self.mj_input)
        self.add_item(self.name_input)
        self.add_item(self.actions_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=False)
        channel = self.cog.bot.get_channel(SCENE_CHANNEL_ID)
        if not channel:
            return
        actions = [a.strip() for a in self.actions_input.value.splitlines() if a.strip()]
        await self.cog.create_scene(
            channel,
            self.name_input.value.strip(),
            self.mj_input.value.strip(),
            actions,
        )


class ActionButton(discord.ui.Button):
    def __init__(self, cog: "SceneTodo", scene_id: int, action: dict):
        style = discord.ButtonStyle.success if action.get("done") else discord.ButtonStyle.secondary
        super().__init__(
            label=action["label"],
            style=style,
            custom_id=f"scene_{scene_id}_action_{action['id']}",
            disabled=action.get("done", False),
        )
        self.cog = cog
        self.scene_id = scene_id
        self.action_id = action["id"]

    async def callback(self, interaction: discord.Interaction):
        if not any(r.id == MJ_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("Permission refusée.")
            return
        scene = self.cog.get_scene(self.scene_id)
        if not scene:
            await interaction.response.send_message("Scène introuvable.")
            return
        action = self.cog.toggle_action(self.scene_id, self.action_id)
        if not action:
            await interaction.response.send_message("Action introuvable.")
            return
        await interaction.response.defer(thinking=False)
        await self.cog.refresh_scene_message(scene)
        if action.get("done"):
            await self.cog.log_action_done(scene, action, interaction.user)


class CompleteButton(discord.ui.Button):
    def __init__(self, cog: "SceneTodo", scene_id: int, disabled: bool):
        super().__init__(
            label="Scène terminée",
            style=discord.ButtonStyle.success,
            custom_id=f"scene_done_{scene_id}",
            disabled=disabled,
        )
        self.cog = cog
        self.scene_id = scene_id

    async def callback(self, interaction: discord.Interaction):
        if not any(r.id == MJ_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("Permission refusée.")
            return
        scene = self.cog.get_scene(self.scene_id)
        if not scene:
            await interaction.response.send_message("Scène introuvable.")
            return
        if scene.get("completed"):
            await interaction.response.send_message("Scène déjà terminée.")
            return
        await self.cog.finish_scene(scene)
        await interaction.response.defer(thinking=False)


class DeleteSceneButton(discord.ui.Button):
    def __init__(self, cog: "SceneTodo", scene_id: int):
        super().__init__(
            label="Supprimer",
            style=discord.ButtonStyle.danger,
            custom_id=f"scene_del_{scene_id}",
        )
        self.cog = cog
        self.scene_id = scene_id

    async def callback(self, interaction: discord.Interaction):
        if not any(r.id == MJ_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("Permission refusée.")
            return
        scene = self.cog.delete_scene(self.scene_id)
        if not scene:
            await interaction.response.send_message("Scène introuvable.")
            return
        await interaction.response.defer(thinking=False)
        channel = self.cog.bot.get_channel(SCENE_CHANNEL_ID)
        if channel:
            try:
                msg = await channel.fetch_message(scene["message_id"])
                await msg.delete()
            except discord.NotFound:
                pass


class SceneView(discord.ui.View):
    def __init__(self, cog: "SceneTodo", scene: dict):
        super().__init__(timeout=None)
        for action in scene.get("actions", []):
            self.add_item(ActionButton(cog, scene["id"], action))
        self.add_item(CompleteButton(cog, scene["id"], scene.get("completed", False)))
        self.add_item(DeleteSceneButton(cog, scene["id"]))


class AddSceneView(discord.ui.View):
    def __init__(self, cog: "SceneTodo"):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(AddSceneButton(cog))


class AddSceneButton(discord.ui.Button):
    def __init__(self, cog: "SceneTodo"):
        super().__init__(label="Ajouter une scène", style=discord.ButtonStyle.primary, custom_id="create_scene")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if not any(r.id == MJ_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("Permission refusée.")
            return
        await interaction.response.send_modal(AddSceneModal(self.cog))


class SceneTodo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        data = self.load_data()
        self.scenes = data.get("scenes", [])
        self.init_message_id = data.get("init_message")
        self.bot.loop.create_task(self.initialize())

    # ---------------- Persistence ----------------
    def load_data(self):
        if os.path.isfile(SCENES_FILE):
            with open(SCENES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                data = {"scenes": data, "init_message": None}
            if "message" in data and "init_message" not in data:
                data["init_message"] = data["message"]
            for scene in data.get("scenes", []):
                scene.setdefault("completed", False)
                scene.setdefault("actions", [])
            return data
        return {"scenes": [], "init_message": None}

    def save_data(self):
        with open(SCENES_FILE, "w", encoding="utf-8") as f:
            json.dump({"scenes": self.scenes, "init_message": self.init_message_id}, f, ensure_ascii=False, indent=2)

    # ---------------- Utility ----------------
    def get_scene(self, scene_id: int):
        for s in self.scenes:
            if s["id"] == scene_id:
                return s
        return None

    def add_action(self, scene_id: int, label: str):
        scene = self.get_scene(scene_id)
        if not scene:
            return None
        action_id = max([a["id"] for a in scene.get("actions", [])], default=0) + 1
        action = {"id": action_id, "label": label, "done": False}
        scene.setdefault("actions", []).append(action)
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
        for i, scene in enumerate(self.scenes):
            if scene["id"] == scene_id:
                removed = self.scenes.pop(i)
                self.save_data()
                return removed
        return None

    def build_scene_embed(self, scene: dict) -> discord.Embed:
        created = datetime.fromisoformat(scene["created_at"]).strftime("%d/%m/%Y")
        desc = f"MJ responsable : {scene['mj']}\nCréée le {created}"
        actions = scene.get("actions", [])
        if actions:
            for act in actions:
                status = "✅" if act.get("done") else "⬜️"
                desc += f"\n{status} {act['label']}"
        if scene.get("completed"):
            desc += "\n✅ Scène terminée"
        return discord.Embed(title=scene["name"], description=desc, color=EMBED_COLOR)

    async def log_action_done(self, scene: dict, action: dict, user: discord.User):
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send(
                f"📌 Action **{action['label']}** complétée pour la scène **{scene['name']}** (MJ : {scene['mj']}) par {user.mention}"
            )

    async def log_completion(self, scene: dict):
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send(f"✅ Scène **{scene['name']}** terminée (MJ : {scene['mj']})")

    async def refresh_scene_message(self, scene: dict):
        channel = self.bot.get_channel(SCENE_CHANNEL_ID)
        if not channel:
            return
        try:
            message = await channel.fetch_message(scene["message_id"])
        except discord.NotFound:
            return
        view = SceneView(self, scene)
        await message.edit(embed=self.build_scene_embed(scene), view=view)
        self.bot.add_view(view, message_id=message.id)

    # ---------------- Scene operations ----------------
    async def create_scene(self, channel: discord.TextChannel, name: str, mj: str, actions: list[str]):
        scene_id = max([s["id"] for s in self.scenes], default=0) + 1
        scene = {
            "id": scene_id,
            "name": name,
            "mj": mj,
            "created_at": datetime.utcnow().isoformat(),
            "completed": False,
            "message_id": None,
            "actions": [],
        }
        for i, label in enumerate(actions, start=1):
            scene["actions"].append({"id": i, "label": label, "done": False})
        view = SceneView(self, scene)
        message = await channel.send(embed=self.build_scene_embed(scene), view=view)
        self.bot.add_view(view, message_id=message.id)
        scene["message_id"] = message.id
        self.scenes.append(scene)
        self.save_data()
        return scene

    async def finish_scene(self, scene: dict):
        scene["completed"] = True
        self.save_data()
        await self.refresh_scene_message(scene)
        await self.log_completion(scene)

    # ---------------- Initialization ----------------
    async def initialize(self):
        await self.bot.wait_until_ready()
        await self.ensure_init_message()
        await self.restore_scene_views()

    async def ensure_init_message(self):
        channel = self.bot.get_channel(SCENE_CHANNEL_ID)
        if not channel:
            return
        if self.init_message_id:
            try:
                message = await channel.fetch_message(self.init_message_id)
                view = AddSceneView(self)
                await message.edit(view=view)
                self.bot.add_view(view, message_id=message.id)
                return
            except discord.NotFound:
                self.init_message_id = None
        embed = discord.Embed(title="Gestion des scènes", description="Utilisez le bouton ci-dessous pour créer une nouvelle scène.", color=EMBED_COLOR)
        view = AddSceneView(self)
        message = await channel.send(embed=embed, view=view)
        self.bot.add_view(view, message_id=message.id)
        self.init_message_id = message.id
        self.save_data()

    async def restore_scene_views(self):
        channel = self.bot.get_channel(SCENE_CHANNEL_ID)
        if not channel:
            return
        for scene in self.scenes:
            try:
                message = await channel.fetch_message(scene["message_id"])
            except discord.NotFound:
                continue
            view = SceneView(self, scene)
            await message.edit(embed=self.build_scene_embed(scene), view=view)
            self.bot.add_view(view, message_id=message.id)

    # ---------------- Commands ----------------
    @app_commands.command(name="scenes-init", description="Réinitialiser le message de création de scènes")
    async def scenes_init(self, interaction: discord.Interaction):
        if not any(r.id == MJ_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("Permission refusée.")
            return
        await self.ensure_init_message()
        await interaction.response.send_message("Message initial prêt.")


async def setup(bot: commands.Bot):
    await bot.add_cog(SceneTodo(bot))
    print("Cog scene_todo chargé avec succès")
