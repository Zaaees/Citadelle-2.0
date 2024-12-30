import discord
from discord.ext import commands
from discord import app_commands
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

class ValidationFiche(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.setup_google_sheets()

    def setup_google_sheets(self):
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = json.loads(os.getenv('SERVICE_ACCOUNT_JSON'))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        self.gc = gspread.authorize(creds)
        self.sheet = self.gc.open_by_key(os.getenv('GOOGLE_SHEET_ID_VALIDATION')).sheet1

    def get_ticket_data(self, channel_id):
        try:
            cell = self.sheet.find(str(channel_id))
            if cell:
                row = self.sheet.row_values(cell.row)
                validations = json.loads(row[1]) if row[1] else {}
                corrections = json.loads(row[2]) if row[2] else {}
                return validations, corrections
            return {}, {}
        except:
            return {}, {}

    def save_ticket_data(self, channel_id, validations, corrections):
        try:
            cell = self.sheet.find(str(channel_id))
            row = [str(channel_id), json.dumps(validations), json.dumps(corrections)]
            if cell:
                self.sheet.update('A{}:C{}'.format(cell.row, cell.row), [row])
            else:
                self.sheet.append_row(row)
        except Exception as e:
            print(f"Error saving data: {e}")

    class ValidateModal(discord.ui.Modal):
        def __init__(self):
            super().__init__(title="Points à corriger")
            self.corrections = discord.ui.TextInput(
                label="Corrections nécessaires",
                style=discord.TextStyle.paragraph,
                required=True
            )
            self.add_item(self.corrections)

    class ValidateButtons(discord.ui.View):
        def __init__(self, cog):
            super().__init__(timeout=None)
            self.cog = cog

        def create_embed(self, validations, corrections):
            embed = discord.Embed(title="Validation de la fiche", color=discord.Color.blue())
           
            validations_text = "\n".join([f"• {self.cog.bot.get_user(int(user_id)).name}" 
                                        for user_id in validations]) or "Aucune validation"
            embed.add_field(name="Validations", value=validations_text, inline=False)
           
            corrections_text = ""
            for user_id, user_corrections in corrections.items():
                user = self.cog.bot.get_user(int(user_id))
                corrections_text += f"**{user.name}**:\n"
                for correction in user_corrections:
                    corrections_text += f"• {correction}\n"
           
            embed.add_field(name="Corrections demandées", 
                          value=corrections_text or "Aucune correction demandée", 
                          inline=False)
            return embed

        @discord.ui.button(label="Validé", style=discord.ButtonStyle.green, custom_id="validate")
        async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not any(role.id == 1018179623886000278 for role in interaction.user.roles):
                await interaction.response.send_message("Vous n'avez pas la permission.", ephemeral=True)
                return

            validations, corrections = self.cog.get_ticket_data(interaction.channel_id)
            user_id = str(interaction.user.id)

            if user_id in validations:
                validations.pop(user_id)
                corrections.pop(user_id, None)
            else:
                validations[user_id] = True
                corrections.pop(user_id, None)

            self.cog.save_ticket_data(interaction.channel_id, validations, corrections)
            await interaction.message.edit(embed=self.create_embed(validations, corrections))
            await interaction.response.defer()

        @discord.ui.button(label="À corriger", style=discord.ButtonStyle.red, custom_id="correct")
        async def correct(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not any(role.id == 1018179623886000278 for role in interaction.user.roles):
                await interaction.response.send_message("Vous n'avez pas la permission.", ephemeral=True)
                return

            modal = ValidationFiche.ValidateModal()
           
            async def modal_callback(interaction: discord.Interaction):
                validations, corrections = self.cog.get_ticket_data(interaction.channel_id)
                user_id = str(interaction.user.id)
               
                if user_id in validations:
                    validations.pop(user_id)
               
                if user_id not in corrections:
                    corrections[user_id] = []
                corrections[user_id].append(modal.corrections.value)
               
                self.cog.save_ticket_data(interaction.channel_id, validations, corrections)
                await interaction.message.edit(embed=self.create_embed(validations, corrections))
           
            modal.on_submit = modal_callback
            await interaction.response.send_modal(modal)

    async def create_validation_message(self, channel):
        embed = discord.Embed(title="Validation de la fiche", color=discord.Color.blue())
        embed.add_field(name="Validations", value="Aucune validation pour le moment", inline=False)
        embed.add_field(name="Corrections demandées", value="Aucune correction demandée", inline=False)
       
        view = self.ValidateButtons(self)
        message = await channel.send(embed=embed, view=view)
        await message.pin()
        return message

    async def check_and_create_validation_messages(self):
        for guild in self.bot.guilds:
            category = guild.get_channel(1020827427888435210)
            if category:
                for channel in category.channels:
                    if channel.name.startswith("【🎭】"):
                        messages = [msg async for msg in channel.history()]
                        existing = any(msg.author == self.bot.user and 
                                    msg.embeds and 
                                    msg.embeds[0].title == "Validation de la fiche" 
                                    for msg in messages)
                        if not existing:
                            await self.create_validation_message(channel)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.check_and_create_validation_messages()

    @app_commands.command(name="validation")
    @app_commands.default_permissions(administrator=True)
    async def validation(self, interaction: discord.Interaction):
        await self.create_validation_message(interaction.channel)
        await interaction.response.send_message("Message de validation créé.", ephemeral=True)
 
async def setup(bot):
    await bot.add_cog(ValidationFiche(bot))