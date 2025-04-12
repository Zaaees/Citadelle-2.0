import os

# Extensions d'image reconnues
image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}

def count_images_in_directory(directory):
    count = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            if os.path.splitext(file)[1].lower() in image_extensions:
                count += 1
    return count

# Exemple d'utilisation
dossier = "C:/Users/freed/OneDrive/Pictures/La Citadelle du temps/Cartes"
nombre_images = count_images_in_directory(dossier)
print(f"Nombre d'images dans '{dossier}' et ses sous-dossiers : {nombre_images}")
