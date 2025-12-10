/**
 * Types pour le système de cartes Citadelle
 * Correspond exactement au système du bot Discord
 */

// Catégories de cartes (ordre de rareté décroissante)
export const ALL_CATEGORIES = [
  'Secrète',
  'Fondateur',
  'Historique',
  'Maître',
  'Black Hole',
  'Architectes',
  'Professeurs',
  'Autre',
  'Élèves',
] as const

export type CardCategory = (typeof ALL_CATEGORIES)[number]

// Poids de rareté (probabilités de tirage)
export const RARITY_WEIGHTS: Record<CardCategory, number> = {
  Secrète: 0.005,
  Fondateur: 0.01,
  Historique: 0.02,
  Maître: 0.06,
  'Black Hole': 0.06,
  Architectes: 0.07,
  Professeurs: 0.1167,
  Autre: 0.2569,
  Élèves: 0.4203,
}

// Couleurs par catégorie pour l'UI
export const CATEGORY_COLORS: Record<CardCategory, { bg: string; border: string; text: string }> = {
  Secrète: {
    bg: 'from-purple-900 via-pink-900 to-purple-900',
    border: 'border-purple-500',
    text: 'text-purple-300',
  },
  Fondateur: {
    bg: 'from-yellow-900 via-amber-900 to-yellow-900',
    border: 'border-yellow-500',
    text: 'text-yellow-300',
  },
  Historique: {
    bg: 'from-blue-900 via-indigo-900 to-blue-900',
    border: 'border-blue-500',
    text: 'text-blue-300',
  },
  Maître: {
    bg: 'from-red-900 via-rose-900 to-red-900',
    border: 'border-red-500',
    text: 'text-red-300',
  },
  'Black Hole': {
    bg: 'from-gray-900 via-slate-900 to-gray-900',
    border: 'border-gray-500',
    text: 'text-gray-300',
  },
  Architectes: {
    bg: 'from-cyan-900 via-teal-900 to-cyan-900',
    border: 'border-cyan-500',
    text: 'text-cyan-300',
  },
  Professeurs: {
    bg: 'from-green-900 via-emerald-900 to-green-900',
    border: 'border-green-500',
    text: 'text-green-300',
  },
  Autre: {
    bg: 'from-orange-900 via-amber-900 to-orange-900',
    border: 'border-orange-500',
    text: 'text-orange-300',
  },
  Élèves: {
    bg: 'from-slate-800 via-gray-800 to-slate-800',
    border: 'border-slate-500',
    text: 'text-slate-300',
  },
}

// Interface pour une carte
export interface Card {
  category: CardCategory
  name: string // Nom sans .png
  file_id: string | null
  is_full: boolean
  rarity_weight: number
}

// Interface pour une carte dans une collection utilisateur
export interface CardInCollection extends Card {
  count: number // Nombre d'exemplaires possédés
}

// Informations sur une catégorie
export interface CategoryInfo {
  category: CardCategory
  weight: number
  total_cards: number
  percentage: number
}
