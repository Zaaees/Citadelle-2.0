import discord
from discord.ext import commands
import json
import asyncio
from datetime import datetime

class ElementSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Terre", value="Terre", emoji="🌍"),
            discord.SelectOption(label="Feu", value="Feu", emoji="🔥"),
            discord.SelectOption(label="Vent", value="Vent", emoji="💨"),
            discord.SelectOption(label="Eau", value="Eau", emoji="💧"),
            discord.SelectOption(label="Espace", value="Espace", emoji="🌌")
        ]
        super().__init__(placeholder="Choisir un élément", options=options, min_values=1, max_values=1)

class SousElementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ElementSelect())

class Souselement2(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.element_channels = {
            "Terre": 1137675703630970891,
            "Eau": 1137675658609303552,
            "Vent": 1137675592125399122,
            "Feu": 1137675742499573861,
            "Espace": 1137675462076796949
        }
        self.forum_id = 1137670941820846150

    @commands.command()
    async def creersouselement(self, ctx):
        """Crée un nouveau sous-élément"""
        # Vérifier si l'utilisateur est dans un salon approprié
        if isinstance(ctx.channel, discord.DMChannel):
            return await ctx.send("Cette commande doit être utilisée dans un serveur.")

        questions = [
            "Quel est le nom du sous-élément ?",
            "Quelle est la description scientifique du sous-élément ?",
            "Quel est le nom de l'émotion associée ?",
            "Quelle est la description de l'émotion ?",
            "Qui a découvert ce sous-élément ? (Mentionnez le joueur)"
        ]

        reponses = []
        view = SousElementView()
        await ctx.send("Choisissez l'élément principal:", view=view)
        
        try:
            interaction = await self.bot.wait_for(
                "select_option",
                timeout=60.0,
                check=lambda i: i.user == ctx.author
            )
            element_principal = interaction.values[0]
        except asyncio.TimeoutError:
            return await ctx.send("Temps écoulé. Veuillez réessayer.")

        for question in questions:
            await ctx.send(question)
            try:
                reponse = await self.bot.wait_for(
                    "message",
                    timeout=300.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel
                )
                reponses.append(reponse.content)
            except asyncio.TimeoutError:
                return await ctx.send("Temps écoulé. Veuillez réessayer.")

        # Création de l'embed
        embed = discord.Embed(
            title=f"Nouveau sous-élément : {reponses[0]}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Élément principal", value=element_principal, inline=False)
        embed.add_field(name="Description scientifique", value=reponses[1], inline=False)
        embed.add_field(name="Émotion", value=reponses[2], inline=False)
        embed.add_field(name="Description de l'émotion", value=reponses[3], inline=False)
        embed.add_field(name="Découvert par", value=reponses[4], inline=False)
        embed.add_field(name="Utilisé par", value="Personne pour le moment", inline=False)

        # Envoyer dans le fil approprié
        channel = self.bot.get_channel(self.element_channels[element_principal])
        if channel:
            await channel.send(embed=embed)
            await ctx.send("Sous-élément créé avec succès!")

    @commands.command()
    async def fichesouselement(self, ctx):
        """Crée une fiche de sous-éléments pour un utilisateur"""
        embed = discord.Embed(
            title=f"Fiche de sous-éléments de {ctx.author.name}",
            description="Utilisez les boutons pour ajouter des sous-éléments à votre fiche.",
            color=discord.Color.green()
        )
        
        for element in ["Terre", "Feu", "Vent", "Eau", "Espace"]:
            embed.add_field(name=element, value="Aucun sous-élément", inline=False)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Souselement2(bot))
