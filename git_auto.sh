#!/bin/bash

echo "Entrez le message de commit :"
read commit_message

# Ajouter tous les fichiers
git add .

# Faire le commit avec un message par défaut
git commit -m "$commit_message"

# Pousser les modifications
git push origin main --force