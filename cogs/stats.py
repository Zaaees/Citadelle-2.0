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
        total_channels = len(interaction.guild.text_channels)
        progress_message = await interaction.followup.send("Analyse en cours... Veuillez patienter.")
        
        update_threshold = 1000  # Mettre à jour tous les 1000 messages
        last_update = 0
        current_channel = ""
        
        # Analyser tous les canaux textuels du serveur
        for idx, channel in enumerate(interaction.guild.text_channels, 1):
            try:
                current_channel = channel.name
                async for message in channel.history(limit=None):
                    if message.content and not message.author.bot:
                        lengths.append(len(message.content))
                        
                        # Mettre à jour le message de progression moins fréquemment
                        if len(lengths) - last_update >= update_threshold:
                            await progress_message.edit(content=(
                                f"Analyse en cours...\n"
                                f"Canal actuel ({idx}/{total_channels}) : {current_channel}\n"
                                f"Messages analysés : {len(lengths)}"
                            ))
                            last_update = len(lengths)
                            
            except discord.Forbidden:
                print(f"Accès refusé au canal : {channel.name}")
                continue
            except Exception as e:
                print(f"Erreur dans le canal {channel.name}: {str(e)}")
                continue

        # Message final avant l'analyse
        await progress_message.edit(content=(
            f"Analyse terminée !\n"
            f"Canaux analysés : {idx}/{total_channels}\n"
            f"Total messages : {len(lengths)}\n"
            f"Génération du graphique en cours..."
        ))

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
