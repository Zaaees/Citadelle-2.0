import type { Card } from '../../types/card'
import CardItem from './CardItem'
import { Loader2, PackageOpen } from 'lucide-react'

interface CardGridProps {
  cards: Card[]
  loading?: boolean
  error?: Error | null
  emptyMessage?: string
  onCardClick?: (card: Card) => void
  userCardCounts?: Record<string, number> // Key: `${category}:${name}`
}

export default function CardGrid({
  cards,
  loading = false,
  error = null,
  emptyMessage = 'Aucune carte à afficher',
  onCardClick,
  userCardCounts,
}: CardGridProps) {
  // État de chargement
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <Loader2 className="w-12 h-12 text-primary animate-spin mb-4" />
        <p className="text-gray-400">Chargement des cartes...</p>
      </div>
    )
  }

  // État d'erreur
  if (error) {
    return (
      <div className="card text-center py-12">
        <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
          <PackageOpen className="w-8 h-8 text-red-500" />
        </div>
        <h3 className="text-xl font-display font-bold text-white mb-2">
          Erreur de chargement
        </h3>
        <p className="text-gray-400">{error.message}</p>
      </div>
    )
  }

  // État vide
  if (cards.length === 0) {
    return (
      <div className="card text-center py-12">
        <div className="w-16 h-16 bg-dark-700 rounded-full flex items-center justify-center mx-auto mb-4">
          <PackageOpen className="w-8 h-8 text-gray-500" />
        </div>
        <h3 className="text-xl font-display font-bold text-white mb-2">{emptyMessage}</h3>
        <p className="text-gray-400">Aucune carte ne correspond à vos critères</p>
      </div>
    )
  }

  // Grille de cartes
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
      {cards.map((card, index) => {
        const cardKey = `${card.category}:${card.name}`
        const count = userCardCounts?.[cardKey]

        return (
          <CardItem
            key={`${card.category}-${card.name}-${index}`}
            card={card}
            count={count}
            onClick={() => onCardClick?.(card)}
          />
        )
      })}
    </div>
  )
}
