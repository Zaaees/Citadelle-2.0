import discord
from discord.ext import commands
from discord import app_commands
import numpy as np
import matplotlib.pyplot as plt
import io

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def benford_law(self):
        # Retourne la distribution théorique de Benford
        return [np.log10(1 + 1/d) * 100 for d in range(1, 10)]

    def get_first_digit(self, number):
        # Retourne le premier chiffre d'un nombre
        return int(str(abs(number))[0])

    @app_commands.command(name="analyse_messages", description="Analyse les longueurs des messages de tout le serveur")
    async def analyse_messages(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        lengths = []
        progress_message = await interaction.followup.send("Analyse en cours... Veuillez patienter.")
        
        # Analyser tous les canaux textuels du serveur
        for channel in interaction.guild.text_channels:
            try:
                async for message in channel.history(limit=None):
                    if message.content and not message.author.bot:  # Ignorer messages vides et messages de bots
                        lengths.append(len(message.content))
                await progress_message.edit(content=f"Analyse en cours... {len(lengths)} messages analysés.")
            except discord.Forbidden:
                continue  # Ignorer les canaux inaccessibles
            
        if not lengths:
            await progress_message.edit(content="Aucun message trouvé pour l'analyse.")
            return

        # Obtenir les premiers chiffres
        first_digits = [self.get_first_digit(length) for length in lengths]
        
        # Calculer la distribution observée
        observed_counts = [first_digits.count(i) for i in range(1, 10)]
        total_counts = sum(observed_counts)
        observed_distribution = [count/total_counts * 100 for count in observed_counts]

        # Obtenir la distribution de Benford
        benford_distribution = self.benford_law()

        # Créer le graphique
        plt.figure(figsize=(10, 6))
        x = range(1, 10)
        plt.bar(x, observed_distribution, alpha=0.5, label='Observé', color='blue')
        plt.plot(x, benford_distribution, 'r-', label='Loi de Benford', linewidth=2)
        plt.xlabel('Premier chiffre')
        plt.ylabel('Pourcentage')
        plt.title('Distribution des premiers chiffres vs Loi de Benford')
        plt.legend()
        plt.grid(True)

        # Sauvegarder le graphique en mémoire
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        # Envoyer le graphique
        file = discord.File(buf, filename='stats.png')
        
        # Ajouter plus de statistiques dans le message
        await progress_message.delete()
        await interaction.followup.send(
            f"📊 **Analyse des messages du serveur**\n"
            f"Nombre total de messages analysés : {len(lengths)}\n"
            f"Longueur moyenne : {np.mean(lengths):.2f} caractères\n"
            f"Longueur médiane : {np.median(lengths):.0f} caractères\n"  # Correction ici (::.0f -> :.0f)
            f"Longueur minimale : {min(lengths)} caractères\n"
            f"Longueur maximale : {max(lengths)} caractères",
            file=file
        )

async def setup(bot):
    await bot.add_cog(Stats(bot))
