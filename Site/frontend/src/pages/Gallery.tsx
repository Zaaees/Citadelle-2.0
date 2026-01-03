import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sparkles, ChevronDown, ChevronUp, Package, Loader2 } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import api from '../services/api'
import { ALL_CATEGORIES, CATEGORY_COLORS, FULL_CATEGORY_COLOR } from '../types/card'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface CollectionCard {
  category: string
  name: string
  count: number
  is_full: boolean
  file_id: string | null
}

interface UserCollection {
  cards: CollectionCard[]
  total_cards: number
  unique_cards: number
  completion_percentage: number
}

export default function Gallery() {
  const { isAuthenticated } = useAuthStore()
  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({})

  // Récupérer la collection complète de l'utilisateur
  const { data: collection, isLoading, error } = useQuery({
    queryKey: ['user', 'collection'],
    queryFn: async () => {
      const response = await api.get<UserCollection>('/api/cards/inventory')
      return response.data
    },
    enabled: isAuthenticated,
    retry: 1
  })

  // Grouper les cartes par catégorie
  const cardsByCategory = collection?.cards?.reduce((acc, card) => {
    if (!acc[card.category]) {
      acc[card.category] = []
    }
    acc[card.category].push(card)
    return acc
  }, {} as Record<string, CollectionCard[]>) || {}

  // Compter les cartes Full
  const fullCards = collection?.cards?.filter(c => c.is_full) || []

  // Toggle une catégorie
  const toggleCategory = (category: string) => {
    setExpandedCategories(prev => ({
      ...prev,
      [category]: !prev[category]
    }))
  }

  // URL de l'image de carte
  const getCardImageUrl = (fileId: string | null) => {
    if (!fileId) return null
    return `${API_URL}/api/cards/image/${fileId}`
  }

  // Non authentifié
  if (!isAuthenticated) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="card text-center py-12">
          <Package className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400">Connectez-vous pour voir votre collection</p>
        </div>
      </div>
    )
  }

  // Erreur
  if (error) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="card text-center py-12">
          <p className="text-red-400">Erreur lors du chargement de la collection</p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 bg-gradient-to-br from-primary to-secondary rounded-lg flex items-center justify-center">
            <Sparkles className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-display font-bold text-white">Ma Collection</h1>
            <p className="text-gray-400">Visualisez toutes les cartes que vous possédez</p>
          </div>
        </div>

        {/* Stats rapides */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="card text-center">
            <p className="text-2xl font-bold text-primary">{collection?.total_cards || 0}</p>
            <p className="text-sm text-gray-400">Cartes totales</p>
            <p className="text-xs text-gray-500">(avec doublons)</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-secondary">{collection?.unique_cards || 0}</p>
            <p className="text-sm text-gray-400">Cartes uniques</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-yellow-400">{fullCards.length}</p>
            <p className="text-sm text-gray-400">Cartes Full</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-green-500">{(collection?.completion_percentage || 0).toFixed(1)}%</p>
            <p className="text-sm text-gray-400">Complétion</p>
          </div>
        </div>
      </div>

      {/* Liste par catégories */}
      {isLoading ? (
        <div className="card">
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 text-primary animate-spin" />
          </div>
        </div>
      ) : collection?.cards && collection.cards.length > 0 ? (
        <div className="space-y-4">
          {/* Catégories normales */}
          {ALL_CATEGORIES.map((category) => {
            const categoryCards = cardsByCategory[category] || []
            if (categoryCards.length === 0) return null

            const colors = CATEGORY_COLORS[category]
            const isExpanded = expandedCategories[category] || false
            const totalInCategory = categoryCards.reduce((sum, c) => sum + c.count, 0)

            return (
              <div key={category} className="border border-dark-600 rounded-lg overflow-hidden">
                {/* En-tête de la catégorie (cliquable) */}
                <button
                  onClick={() => toggleCategory(category)}
                  className="w-full px-4 py-3 flex items-center justify-between bg-dark-700 hover:bg-dark-600 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className={`font-bold ${colors?.text || 'text-gray-300'}`}>
                      {category}
                    </span>
                    <span className="text-sm text-gray-400">
                      {categoryCards.length} carte{categoryCards.length > 1 ? 's' : ''} unique{categoryCards.length > 1 ? 's' : ''}
                      {totalInCategory > categoryCards.length && (
                        <span className="text-gray-500"> ({totalInCategory} avec doublons)</span>
                      )}
                    </span>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="w-5 h-5 text-gray-400" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-gray-400" />
                  )}
                </button>

                {/* Liste des cartes (affichée si expandue) */}
                {isExpanded && (
                  <div className="p-4 bg-dark-800">
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                      {categoryCards.map((card, index) => {
                        const imageUrl = getCardImageUrl(card.file_id)
                        return (
                          <div
                            key={`${card.category}-${card.name}-${index}`}
                            className={`relative bg-dark-700 rounded-lg overflow-hidden border-2 transition-colors ${card.is_full
                                ? 'border-yellow-500/50 shadow-lg shadow-yellow-500/20'
                                : 'border-dark-600 hover:border-primary/50'
                              }`}
                          >
                            {/* Image de la carte */}
                            {imageUrl ? (
                              <img
                                src={imageUrl}
                                alt={card.name}
                                className="w-full aspect-[3/4] object-cover"
                                loading="lazy"
                              />
                            ) : (
                              <div className="w-full aspect-[3/4] bg-dark-600 flex items-center justify-center">
                                <span className="text-gray-500 text-xs text-center px-2">
                                  {card.name}
                                </span>
                              </div>
                            )}

                            {/* Nom et quantité */}
                            <div className="p-2 bg-dark-800/90">
                              <p className="text-xs text-white truncate font-medium">
                                {card.name}
                              </p>
                              <div className="flex items-center justify-between mt-1">
                                <span className="text-xs text-gray-400">
                                  x{card.count}
                                </span>
                                {card.is_full && (
                                  <span className="text-xs text-yellow-400 font-bold">
                                    FULL
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Badge de quantité si > 1 */}
                            {card.count > 1 && (
                              <div className="absolute top-2 right-2 bg-accent/90 text-white text-xs font-bold px-2 py-1 rounded-full">
                                x{card.count}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          {/* Catégorie spéciale Full */}
          {fullCards.length > 0 && (
            <div className="border border-yellow-500/50 rounded-lg overflow-hidden">
              <button
                onClick={() => toggleCategory('full')}
                className="w-full px-4 py-3 flex items-center justify-between bg-gradient-to-r from-yellow-900/30 to-amber-900/30 hover:from-yellow-900/40 hover:to-amber-900/40 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className={`font-bold ${FULL_CATEGORY_COLOR.text}`}>
                    ⭐ Cartes Full
                  </span>
                  <span className="text-sm text-yellow-200/70">
                    {fullCards.length} carte{fullCards.length > 1 ? 's' : ''} Full
                  </span>
                </div>
                {expandedCategories['full'] ? (
                  <ChevronUp className="w-5 h-5 text-yellow-400" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-yellow-400" />
                )}
              </button>

              {expandedCategories['full'] && (
                <div className="p-4 bg-dark-800">
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                    {fullCards.map((card, index) => {
                      const imageUrl = getCardImageUrl(card.file_id)
                      return (
                        <div
                          key={`full-${card.category}-${card.name}-${index}`}
                          className="relative bg-dark-700 rounded-lg overflow-hidden border-2 border-yellow-500/50 shadow-lg shadow-yellow-500/20"
                        >
                          {imageUrl ? (
                            <img
                              src={imageUrl}
                              alt={card.name}
                              className="w-full aspect-[3/4] object-cover"
                              loading="lazy"
                            />
                          ) : (
                            <div className="w-full aspect-[3/4] bg-gradient-to-br from-yellow-900/30 to-amber-900/30 flex items-center justify-center">
                              <span className="text-yellow-400 text-xs text-center px-2">
                                {card.name}
                              </span>
                            </div>
                          )}

                          <div className="p-2 bg-dark-800/90">
                            <p className="text-xs text-yellow-400 truncate font-bold">
                              {card.name}
                            </p>
                            <p className="text-xs text-gray-500 mt-1">
                              {card.category}
                            </p>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="card text-center py-12">
          <Package className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400">Votre collection est vide</p>
          <p className="text-sm text-gray-500 mt-2">
            Effectuez des tirages pour obtenir des cartes !
          </p>
        </div>
      )}
    </div>
  )
}
