import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import json
import os
import gspread
from google.oauth2.service_account import Credentials

SCENE_CHANNEL_ID = 1380704586016362626
LOG_CHANNEL_ID = 1097883902279946360
MJ_ROLE_ID = 1018179623886000278
EMBED_COLOR = 0x6d5380
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


class AddSceneModal(discord.ui.Modal, title="Créer une scène"):
    def __init__(self, cog: "SceneTodo"):
        super().__init__()
        self.cog = cog
        self.mj_input = discord.ui.TextInput(label="MJ responsable", required=True)
        self.name_input = discord.ui.TextInput(label="Nom de la scène", required=True)
        self.add_item(self.mj_input)
        self.add_item(self.name_input)
        

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=False)
        channel = self.cog.bot.get_channel(SCENE_CHANNEL_ID)
        if not channel:
            return
        await self.cog.create_scene(
            channel,
            self.name_input.value.strip(),
            self.mj_input.value.strip(),
        )


class ActionButton(discord.ui.Button):
    def __init__(self, cog: "SceneTodo", scene_id: int):
        super().__init__(
            label="Action terminée",
            style=discord.ButtonStyle.secondary,
            custom_id=f"scene_{scene_id}_action",
        )
        self.cog = cog
        self.scene_id = scene_id

    async def callback(self, interaction: discord.Interaction):
        if not any(r.id == MJ_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("Permission refusée.")
            return
        await interaction.response.defer(thinking=False)
        await interaction.channel.send("Action terminée")


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
        self.add_item(ActionButton(cog, scene["id"]))
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
        self.gc = None
        self.sheet_scenes = None
        self.sheet_config = None
        self.setup_google_sheets()
        data = self.load_data()
        self.scenes = data.get("scenes", [])
        self.init_message_id = data.get("init_message")
        self.bot.loop.create_task(self.initialize())

    def setup_google_sheets(self):
        sheet_id = os.getenv('SCENES_GOOGLE_SHEET_ID')
        if not sheet_id:
            print("SCENES_GOOGLE_SHEET_ID non défini")
            return
        try:
            creds_info = json.loads(os.getenv('SERVICE_ACCOUNT_JSON'))
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
            self.gc = gspread.authorize(creds)
            spreadsheet = self.gc.open_by_key(sheet_id)
            try:
                self.sheet_scenes = spreadsheet.worksheet('Scenes')
            except gspread.exceptions.WorksheetNotFound:
                self.sheet_scenes = spreadsheet.sheet1
                if not self.sheet_scenes.get_all_values():
                    self.sheet_scenes.update('A1', [["id", "name", "mj", "created_at", "completed", "message_id"]])
            try:
                self.sheet_config = spreadsheet.worksheet('Config')
            except gspread.exceptions.WorksheetNotFound:
                self.sheet_config = spreadsheet.add_worksheet(title='Config', rows='10', cols='2')
                self.sheet_config.append_row(["key", "value"])
        except Exception as e:
            print(f"Erreur lors de la connexion à Google Sheets: {e}")
            self.gc = None
            self.sheet_scenes = None
            self.sheet_config = None

    # ---------------- Persistence ----------------
    def load_data(self):
        if not self.sheet_scenes or not self.sheet_config:
            return {"scenes": [], "init_message": None}

        scenes = []
        try:
            rows = self.sheet_scenes.get_all_values()
            header = rows[0] if rows else []
            for row in rows[1:]:
                if not row or not row[0]:
                    continue
                scene = {
                    "id": int(row[0]),
                    "name": row[1],
                    "mj": row[2],
                    "created_at": row[3],
                    "completed": row[4].lower() == "true",
                    "message_id": int(row[5]) if len(row) > 5 and row[5] else None,
                }
                scenes.append(scene)
        except Exception as e:
            print(f"Erreur chargement scenes: {e}")

        init_message = None
        try:
            records = self.sheet_config.get_all_records()
            for rec in records:
                if rec.get("key") == "init_message_id":
                    value = rec.get("value")
                    if value:
                        try:
                            init_message = int(value)
                        except ValueError:
                            init_message = None
                    break
        except Exception as e:
            print(f"Erreur chargement config: {e}")

        return {"scenes": scenes, "init_message": init_message}

    def save_data(self):
        if not self.sheet_scenes or not self.sheet_config:
            return

        try:
            rows = [["id", "name", "mj", "created_at", "completed", "message_id"]]
            for s in self.scenes:
                rows.append([
                    str(s["id"]),
                    s["name"],
                    s["mj"],
                    s["created_at"],
                    str(s.get("completed", False)),
                    str(s.get("message_id", "")),
                ])
            self.sheet_scenes.clear()
            self.sheet_scenes.update('A1', rows)
        except Exception as e:
            print(f"Erreur sauvegarde scenes: {e}")

        try:
            self.sheet_config.clear()
            self.sheet_config.update('A1', [["key", "value"], ["init_message_id", str(self.init_message_id or "")]])
        except Exception as e:
            print(f"Erreur sauvegarde config: {e}")

    # ---------------- Utility ----------------
    def get_scene(self, scene_id: int):
        for s in self.scenes:
            if s["id"] == scene_id:
                return s
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
        if scene.get("completed"):
            desc += "\n✅ Scène terminée"
        return discord.Embed(title=scene["name"], description=desc, color=EMBED_COLOR)

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
    async def create_scene(self, channel: discord.TextChannel, name: str, mj: str):
        scene_id = max([s["id"] for s in self.scenes], default=0) + 1
        scene = {
            "id": scene_id,
            "name": name,
            "mj": mj,
            "created_at": datetime.utcnow().isoformat(),
            "completed": False,
            "message_id": None,
        }
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

