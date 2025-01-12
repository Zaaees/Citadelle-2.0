#!/bin/bash

# Afficher les 5 derniers commits
echo "Les 5 derniers commits :"
echo "------------------------"
git log -n 5 --pretty=format:"%h - %s (%cr)"
echo -e "\n------------------------\n"

echo "Entrez le message de commit :"
read commit_message

# Ajouter tous les fichiers
git add .

# Faire le commit avec un message par défaut
git commit -m "$commit_message"

# Pousser les modifications
git push origin main --force