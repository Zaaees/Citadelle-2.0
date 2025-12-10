import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sparkles, Trophy, Calendar, TrendingUp, Loader2, ChevronDown, ChevronUp, Package } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { authService } from '../services/auth'
import api from '../services/api'
import { ALL_CATEGORIES, CATEGORY_COLORS } from '../types/card'

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

interface UserStats {
  user: {
    user_id: number
    username: string
    avatar: string | null
    global_name: string | null
  }
  total_cards: number
  unique_cards: number
  full_cards: number
  completion_percentage: number
  total_available_cards: number
  cards_by_rarity: Record<string, number>
  bonus_available: number
  can_daily_draw: boolean
  can_sacrificial_draw: boolean
  weekly_exchanges_used: number
  weekly_exchanges_remaining: number
  discoveries_count: number
}

export default function Profile() {
  const { user } = useAuthStore()
  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({})

  // Recuperer les statistiques de l'utilisateur
  const { data: stats, isLoading: statsLoading, error } = useQuery({
    queryKey: ['user', 'stats'],
    queryFn: async () => {
      const response = await api.get<UserStats>('/api/user/stats')
      return response.data
    },
    retry: 1
  })

  // Recuperer la collection complete de l'utilisateur
  const { data: collection, isLoading: collectionLoading } = useQuery({
    queryKey: ['user', 'collection'],
    queryFn: async () => {
      const response = await api.get<UserCollection>('/api/user/collection')
      return response.data
    },
    retry: 1
  })

  // Grouper les cartes par categorie
  const cardsByCategory = collection?.cards?.reduce((acc, card) => {
    if (!acc[card.category]) {
      acc[card.category] = []
    }
    acc[card.category].push(card)
    return acc
  }, {} as Record<string, CollectionCard[]>) || {}

  // Toggle une categorie
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

  if (!user) {
    return null
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="card text-center py-12">
          <p className="text-red-400">Erreur lors du chargement des statistiques</p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header avec avatar */}
      <div className="card mb-8 bg-gradient-to-br from-dark-800 to-dark-900">
        <div className="flex flex-col md:flex-row items-center gap-6">
          {/* Avatar */}
          <div className="relative">
            <img
              src={authService.getAvatarUrl(user)}
              alt={user.username}
              className="w-32 h-32 rounded-full border-4 border-primary shadow-xl"
            />
            <div className="absolute -bottom-2 -right-2 w-10 h-10 bg-gradient-to-br from-primary to-secondary rounded-full flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
          </div>

          {/* Infos utilisateur */}
          <div className="text-center md:text-left">
            <h1 className="text-3xl font-display font-bold text-white">
              {user.global_name || user.username}
            </h1>
            <p className="text-gray-400">@{user.username}</p>

            {/* Badges */}
            <div className="flex flex-wrap gap-2 mt-4 justify-center md:justify-start">
              {(stats?.full_cards || 0) > 0 && (
                <span className="px-3 py-1 bg-yellow-500/20 text-yellow-400 rounded-full text-sm font-medium">
                  Collectionneur Full ({stats.full_cards})
                </span>
              )}
              {(stats?.discoveries_count || 0) > 0 && (
                <span className="px-3 py-1 bg-purple-500/20 text-purple-400 rounded-full text-sm font-medium">
                  Decouvreur ({stats.discoveries_count})
                </span>
              )}
              {(stats?.completion_percentage || 0) >= 50 && (
                <span className="px-3 py-1 bg-blue-500/20 text-blue-400 rounded-full text-sm font-medium">
                  Collectionneur Expert
                </span>
              )}
            </div>
          </div>

          {/* Stats rapides */}
          <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 md:mt-0">
            <div className="text-center p-4 bg-dark-700 rounded-lg">
              <p className="text-3xl font-bold text-primary">
                {statsLoading ? <Loader2 className="w-6 h-6 animate-spin mx-auto" /> : stats?.total_cards || 0}
              </p>
              <p className="text-xs text-gray-400">Cartes totales</p>
              <p className="text-xs text-gray-500">(avec doublons)</p>
            </div>
            <div className="text-center p-4 bg-dark-700 rounded-lg">
              <p className="text-3xl font-bold text-secondary">
                {statsLoading ? <Loader2 className="w-6 h-6 animate-spin mx-auto" /> : stats?.unique_cards || 0}
              </p>
              <p className="text-xs text-gray-400">Cartes uniques</p>
              <p className="text-xs text-gray-500">/{stats?.total_available_cards || '?'} disponibles</p>
            </div>
            <div className="text-center p-4 bg-dark-700 rounded-lg">
              <p className="text-3xl font-bold text-yellow-400">
                {statsLoading ? <Loader2 className="w-6 h-6 animate-spin mx-auto" /> : stats?.full_cards || 0}
              </p>
              <p className="text-xs text-gray-400">Versions Full</p>
            </div>
            <div className="text-center p-4 bg-dark-700 rounded-lg">
              <p className="text-3xl font-bold text-accent">
                {statsLoading ? <Loader2 className="w-6 h-6 animate-spin mx-auto" /> : stats?.discoveries_count || 0}
              </p>
              <p className="text-xs text-gray-400">Decouvertes</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Repartition par categorie */}
        <div className="card">
          <h2 className="text-xl font-display font-bold text-white mb-6 flex items-center gap-2">
            <Trophy className="w-5 h-5 text-accent" />
            Repartition par categorie
          </h2>

          {statsLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-8 h-8 text-primary animate-spin" />
            </div>
          ) : (
            <div className="space-y-3">
              {ALL_CATEGORIES.map((category) => {
                const count = stats?.cards_by_rarity?.[category] || 0
                const totalAvailable = stats?.total_available_cards || 1
                const percentage = totalAvailable > 0 ? (count / totalAvailable) * 100 : 0
                const colors = CATEGORY_COLORS[category]

                return (
                  <div key={category}>
                    <div className="flex items-center justify-between mb-1">
                      <span className={`text-sm font-medium ${colors?.text || 'text-gray-300'}`}>
                        {category}
                      </span>
                      <span className="text-sm text-gray-400">
                        {count} carte{count > 1 ? 's' : ''}
                      </span>
                    </div>
                    <div className="h-2 bg-dark-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full bg-gradient-to-r ${colors?.bg || 'from-gray-500 to-gray-600'} transition-all duration-500`}
                        style={{ width: `${Math.min(percentage * 10, 100)}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Activite */}
        <div className="card">
          <h2 className="text-xl font-display font-bold text-white mb-6 flex items-center gap-2">
            <Calendar className="w-5 h-5 text-primary" />
            Activite
          </h2>

          <div className="space-y-4">
            {/* Tirage journalier */}
            <div className="p-4 bg-dark-700 rounded-lg">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-medium">Tirage journalier</p>
                  <p className="text-sm text-gray-400">
                    {stats?.can_daily_draw ? 'Disponible !' : 'Deja effectue aujourd\'hui'}
                  </p>
                </div>
                <div className={`w-3 h-3 rounded-full ${
                  stats?.can_daily_draw ? 'bg-green-500' : 'bg-red-500'
                }`} />
              </div>
            </div>

            {/* Bonus */}
            <div className="p-4 bg-dark-700 rounded-lg">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-medium">Tirages bonus</p>
                  <p className="text-sm text-gray-400">
                    {stats?.bonus_available || 0} disponible{(stats?.bonus_available || 0) > 1 ? 's' : ''}
                  </p>
                </div>
                <span className="text-2xl font-bold text-accent">
                  {stats?.bonus_available || 0}
                </span>
              </div>
            </div>

            {/* Echanges hebdomadaires */}
            <div className="p-4 bg-dark-700 rounded-lg">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-medium">Echanges hebdomadaires</p>
                  <p className="text-sm text-gray-400">
                    {stats?.weekly_exchanges_remaining ?? 3} restant{(stats?.weekly_exchanges_remaining ?? 3) > 1 ? 's' : ''} cette semaine (reset lundi)
                  </p>
                </div>
                <span className="text-2xl font-bold text-secondary">
                  {stats?.weekly_exchanges_used || 0}/3
                </span>
              </div>
            </div>

            {/* Tirage sacrificiel */}
            <div className="p-4 bg-dark-700 rounded-lg">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-medium">Tirage sacrificiel</p>
                  <p className="text-sm text-gray-400">
                    {stats?.can_sacrificial_draw ? 'Disponible !' : 'Deja effectue aujourd\'hui'}
                  </p>
                </div>
                <div className={`w-3 h-3 rounded-full ${
                  stats?.can_sacrificial_draw ? 'bg-green-500' : 'bg-red-500'
                }`} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Progression */}
      <div className="card mt-6">
        <h2 className="text-xl font-display font-bold text-white mb-6 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-green-400" />
          Progression de collection
        </h2>

        <div className="text-center py-8">
          <div className="relative w-40 h-40 mx-auto mb-6">
            {/* Cercle de progression */}
            <svg className="w-full h-full transform -rotate-90">
              <circle
                cx="80"
                cy="80"
                r="70"
                className="fill-none stroke-dark-700"
                strokeWidth="12"
              />
              <circle
                cx="80"
                cy="80"
                r="70"
                className="fill-none stroke-primary"
                strokeWidth="12"
                strokeDasharray={`${(stats?.completion_percentage || 0) / 100 * 440} 440`}
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-4xl font-bold text-white">
                {(stats?.completion_percentage || 0).toFixed(1)}%
              </span>
              <span className="text-sm text-gray-400">complete</span>
            </div>
          </div>

          <p className="text-gray-400 max-w-md mx-auto">
            Vous avez <span className="text-primary font-bold">{stats?.unique_cards || 0}</span> cartes uniques
            sur <span className="text-secondary font-bold">{stats?.total_available_cards || '?'}</span> disponibles.
            {(stats?.total_cards || 0) > (stats?.unique_cards || 0) && (
              <span className="block mt-2 text-sm">
                Vous possedez egalement <span className="text-accent font-bold">{(stats?.total_cards || 0) - (stats?.unique_cards || 0)}</span> doublons.
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Ma Collection - Liste des cartes avec quantites */}
      <div className="card mt-6">
        <h2 className="text-xl font-display font-bold text-white mb-6 flex items-center gap-2">
          <Package className="w-5 h-5 text-primary" />
          Ma Collection
          <span className="text-sm text-gray-400 font-normal ml-2">
            ({collection?.total_cards || 0} cartes au total)
          </span>
        </h2>

        {collectionLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 text-primary animate-spin" />
          </div>
        ) : collection?.cards && collection.cards.length > 0 ? (
          <div className="space-y-4">
            {ALL_CATEGORIES.map((category) => {
              const categoryCards = cardsByCategory[category] || []
              if (categoryCards.length === 0) return null

              const colors = CATEGORY_COLORS[category]
              const isExpanded = expandedCategories[category] || false
              const totalInCategory = categoryCards.reduce((sum, c) => sum + c.count, 0)

              return (
                <div key={category} className="border border-dark-600 rounded-lg overflow-hidden">
                  {/* En-tete de la categorie (cliquable) */}
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

                  {/* Liste des cartes (affichee si expandue) */}
                  {isExpanded && (
                    <div className="p-4 bg-dark-800">
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                        {categoryCards.map((card, index) => {
                          const imageUrl = getCardImageUrl(card.file_id)
                          return (
                            <div
                              key={`${card.category}-${card.name}-${index}`}
                              className={`relative bg-dark-700 rounded-lg overflow-hidden border-2 transition-colors ${
                                card.is_full
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

                              {/* Nom et quantite */}
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

                              {/* Badge de quantite si > 1 */}
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
          </div>
        ) : (
          <div className="text-center py-12">
            <Package className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">Votre collection est vide</p>
            <p className="text-sm text-gray-500 mt-2">
              Effectuez des tirages pour obtenir des cartes !
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
