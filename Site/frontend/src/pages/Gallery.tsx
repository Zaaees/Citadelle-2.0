import { useState, useMemo } from 'react'
import { Filter, Sparkles, ChevronLeft, ChevronRight } from 'lucide-react'
import { useCards, useCategoriesInfo, useUserCollection } from '../hooks/useCards'
import CardGrid from '../components/cards/CardGrid'
import { ALL_CATEGORIES, CATEGORY_COLORS, type CardCategory } from '../types/card'
import { useAuthStore } from '../stores/authStore'

const CARDS_PER_PAGE = 24

export default function Gallery() {
  const [selectedCategory, setSelectedCategory] = useState<CardCategory | undefined>(undefined)
  const [currentPage, setCurrentPage] = useState(1)
  const { data: cards, isLoading, error } = useCards(selectedCategory)
  const { data: categoriesInfo } = useCategoriesInfo()
  const { data: userCollection } = useUserCollection()
  const { isAuthenticated } = useAuthStore()

  // Filtrer pour n'afficher que les cartes possedees par l'utilisateur
  const ownedCards = useMemo(() => {
    // Si non authentifie, retourner tableau vide (pas de cartes a afficher)
    if (!isAuthenticated) {
      return []
    }

    // Si pas de cartes disponibles, retourner tableau vide
    if (!cards) {
      return []
    }

    // Si la collection n'est pas encore chargee ou est vide, retourner tableau vide
    if (!userCollection?.cards?.length) {
      return []
    }

    // Creer un Set des cartes possedees pour une recherche rapide (avec normalisation)
    const ownedCardKeys = new Set(
      userCollection.cards.map(c => {
        const key = `${c.category.trim()}:${c.name.trim()}`
        return key
      })
    )

    // Filtrer les cartes pour ne garder que celles possedees
    const filtered = cards.filter(card => {
      const key = `${card.category.trim()}:${card.name.trim()}`
      return ownedCardKeys.has(key)
    })

    return filtered
  }, [cards, userCollection, isAuthenticated])

  // Statistiques basées sur la collection de l'utilisateur
  const totalCards = ownedCards?.length || 0
  const fullCards = ownedCards?.filter((c) => c.is_full).length || 0
  const totalQuantity = userCollection?.total_cards || 0

  // Pagination
  const paginatedCards = useMemo(() => {
    if (!ownedCards) return []
    const startIndex = (currentPage - 1) * CARDS_PER_PAGE
    const endIndex = startIndex + CARDS_PER_PAGE
    return ownedCards.slice(startIndex, endIndex)
  }, [ownedCards, currentPage])

  const totalPages = Math.ceil((ownedCards?.length || 0) / CARDS_PER_PAGE)

  // Réinitialiser la page quand on change de catégorie
  const handleCategoryChange = (category: CardCategory | undefined) => {
    setSelectedCategory(category)
    setCurrentPage(1)
  }

  // Créer l'objet userCardCounts pour le CardGrid
  const userCardCounts = useMemo(() => {
    console.log('[Gallery] Computing userCardCounts', {
      isAuthenticated,
      userCollection,
      hasCards: userCollection?.cards?.length
    })

    if (!isAuthenticated || !userCollection?.cards) {
      console.log('[Gallery] No userCardCounts (not authenticated or no cards)')
      return undefined
    }

    const counts: Record<string, number> = {}
    userCollection.cards.forEach((card) => {
      const key = `${card.category}:${card.name}`
      counts[key] = card.count // Fixed: use 'count' instead of 'quantity' to match backend
    })

    console.log('[Gallery] userCardCounts computed:', counts)
    return counts
  }, [isAuthenticated, userCollection])

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
            <p className="text-gray-400">Visualisez toutes les cartes que vous possedez</p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="card text-center">
            <p className="text-2xl font-bold text-primary">{totalCards}</p>
            <p className="text-sm text-gray-400">Cartes totales</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-secondary">{fullCards}</p>
            <p className="text-sm text-gray-400">Cartes Full</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-yellow-500">{ALL_CATEGORIES.length}</p>
            <p className="text-sm text-gray-400">Catégories</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-green-500">{totalCards - fullCards}</p>
            <p className="text-sm text-gray-400">Cartes normales</p>
          </div>
        </div>

        {/* Filtres */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <Filter className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-white">Filtrer par catégorie</h2>
          </div>

          <div className="flex flex-wrap gap-2">
            {/* Bouton "Toutes" */}
            <button
              onClick={() => handleCategoryChange(undefined)}
              className={`
                px-4 py-2 rounded-lg font-medium transition-all
                ${
                  selectedCategory === undefined
                    ? 'bg-gradient-to-r from-primary to-secondary text-white border-2 border-primary'
                    : 'bg-dark-700 text-gray-300 border-2 border-dark-600 hover:border-primary hover:text-white'
                }
              `}
            >
              Toutes ({totalCards})
            </button>

            {/* Boutons de catégories */}
            {ALL_CATEGORIES.map((category) => {
              const colors = CATEGORY_COLORS[category]
              const categoryData = categoriesInfo?.find((c) => c.category === category)
              const count = categoryData?.total_cards || '?'
              const isSelected = selectedCategory === category

              return (
                <button
                  key={category}
                  onClick={() => handleCategoryChange(category)}
                  className={`
                    px-4 py-2 rounded-lg font-medium transition-all
                    border-2 ${colors.border}
                    ${
                      isSelected
                        ? `bg-gradient-to-r ${colors.bg} text-white`
                        : `bg-dark-700 ${colors.text} hover:bg-gradient-to-r ${colors.bg} hover:text-white`
                    }
                  `}
                >
                  {category} ({count})
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Grille de cartes */}
      <CardGrid
        cards={paginatedCards}
        loading={isLoading}
        error={error}
        userCardCounts={userCardCounts}
      />

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="card mt-8">
          <div className="flex items-center justify-between">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all
                ${
                  currentPage === 1
                    ? 'bg-dark-700 text-gray-500 cursor-not-allowed'
                    : 'bg-gradient-to-r from-primary to-secondary text-white hover:shadow-lg hover:shadow-primary/50'
                }
              `}
            >
              <ChevronLeft className="w-5 h-5" />
              Précédent
            </button>

            <div className="flex items-center gap-2">
              <span className="text-gray-400">
                Page <span className="text-white font-bold">{currentPage}</span> sur{' '}
                <span className="text-white font-bold">{totalPages}</span>
              </span>
              <span className="text-gray-500">•</span>
              <span className="text-gray-400">
                {paginatedCards.length} cartes affichées sur {totalCards}
              </span>
            </div>

            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all
                ${
                  currentPage === totalPages
                    ? 'bg-dark-700 text-gray-500 cursor-not-allowed'
                    : 'bg-gradient-to-r from-primary to-secondary text-white hover:shadow-lg hover:shadow-primary/50'
                }
              `}
            >
              Suivant
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
