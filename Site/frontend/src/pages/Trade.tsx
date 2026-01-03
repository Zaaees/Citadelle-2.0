import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search, Store, Send, Inbox, Filter,
  Loader2, X, Check, Clock, AlertCircle, ChevronDown,
  ArrowLeftRight, User, Eye, RefreshCw
} from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../services/api'
import { CATEGORY_COLORS, ALL_CATEGORIES } from '../types/card'
import { useAuthStore } from '../stores/authStore'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Types pour le Bazaar
interface CardInfo {
  category: string
  name: string
  file_id?: string | null
}

interface CardOwner {
  user_id: string
  username: string
  count: number
  available: number
}

interface CardAvailability {
  category: string
  name: string
  file_id?: string | null
  owners: CardOwner[]
  total_available: number
}

interface BazaarSearchResult {
  cards: CardAvailability[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

interface TradeRequest {
  id: string
  requester_id: string
  requester_name: string
  target_id: string
  target_name: string
  offered_card: CardInfo
  requested_card: CardInfo
  status: 'pending' | 'accepted' | 'declined' | 'cancelled' | 'expired'
  created_at: string
  expires_at: string
}

interface UserTradeRequests {
  received: TradeRequest[]
  sent: TradeRequest[]
}

interface MyCard {
  category: string
  name: string
  count: number
  is_full: boolean
  file_id: string | null
}

export default function Trade() {
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState<'bazaar' | 'requests'>('bazaar')

  // Etats pour la recherche
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('')
  const [includeNonDuplicates, setIncludeNonDuplicates] = useState(false)
  const [showCategoryDropdown, setShowCategoryDropdown] = useState(false)

  // Etats pour la proposition d'echange
  const [selectedCard, setSelectedCard] = useState<CardAvailability | null>(null)
  const [selectedOwner, setSelectedOwner] = useState<CardOwner | null>(null)
  const [showTradeModal, setShowTradeModal] = useState(false)
  const [myCardToOffer, setMyCardToOffer] = useState<MyCard | null>(null)

  // Recherche dans le Bazaar
  const { data: searchResults, isLoading: searchLoading, error: searchError, refetch: refetchSearch } = useQuery({
    queryKey: ['bazaar', 'search', searchQuery, selectedCategory, includeNonDuplicates],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (searchQuery) params.append('query', searchQuery)
      if (selectedCategory) params.append('category', selectedCategory)
      if (includeNonDuplicates) params.append('include_non_duplicates', 'true')
      params.append('per_page', '50')

      console.log('[BAZAAR] Searching with params:', params.toString())
      const response = await api.get<BazaarSearchResult>(`/api/bazaar/search?${params}`)
      console.log('[BAZAAR] Search results:', response.data)
      return response.data
    },
    staleTime: 30000,
  })

  // Mes demandes d'echange
  const { data: myRequests, isLoading: requestsLoading } = useQuery({
    queryKey: ['bazaar', 'requests'],
    queryFn: async () => {
      const response = await api.get<UserTradeRequests>('/api/bazaar/requests')
      return response.data
    },
    refetchInterval: 30000, // Rafraichir toutes les 30s
  })

  // Ma collection (pour proposer des cartes)
  const { data: myCollection } = useQuery({
    queryKey: ['user', 'collection'],
    queryFn: async () => {
      const response = await api.get<{ cards: MyCard[] }>('/api/cards/inventory')
      return response.data
    },
  })

  // Mutation pour proposer un echange
  const proposeMutation = useMutation({
    mutationFn: async (data: {
      target_id: string
      offered_category: string
      offered_name: string
      requested_category: string
      requested_name: string
    }) => {
      const response = await api.post('/api/bazaar/propose', data)
      return response.data
    },
    onSuccess: () => {
      toast.success('Demande d\'echange envoyee !')
      queryClient.invalidateQueries({ queryKey: ['bazaar', 'requests'] })
      queryClient.invalidateQueries({ queryKey: ['bazaar', 'search'] })
      setShowTradeModal(false)
      setSelectedCard(null)
      setSelectedOwner(null)
      setMyCardToOffer(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Erreur lors de l\'envoi')
    },
  })

  // Mutation pour accepter un echange
  const acceptMutation = useMutation({
    mutationFn: async (tradeId: string) => {
      const response = await api.post(`/api/bazaar/accept/${tradeId}`)
      return response.data
    },
    onSuccess: () => {
      toast.success('Echange effectue avec succes !')
      queryClient.invalidateQueries({ queryKey: ['bazaar'] })
      queryClient.invalidateQueries({ queryKey: ['user', 'collection'] })
      queryClient.invalidateQueries({ queryKey: ['user', 'stats'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Erreur lors de l\'acceptation')
    },
  })

  // Mutation pour refuser un echange
  const declineMutation = useMutation({
    mutationFn: async (tradeId: string) => {
      const response = await api.post(`/api/bazaar/decline/${tradeId}`)
      return response.data
    },
    onSuccess: () => {
      toast.success('Demande refusee')
      queryClient.invalidateQueries({ queryKey: ['bazaar', 'requests'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Erreur lors du refus')
    },
  })

  // Mutation pour annuler une demande
  const cancelMutation = useMutation({
    mutationFn: async (tradeId: string) => {
      const response = await api.delete(`/api/bazaar/cancel/${tradeId}`)
      return response.data
    },
    onSuccess: () => {
      toast.success('Demande annulee')
      queryClient.invalidateQueries({ queryKey: ['bazaar', 'requests'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Erreur lors de l\'annulation')
    },
  })

  // Cartes eligibles pour l'echange (non-Full, count > 0)
  const eligibleCards = useMemo(() => {
    return myCollection?.cards?.filter(card => !card.is_full && card.count > 0) || []
  }, [myCollection])

  // Formater le temps restant
  const formatTimeRemaining = (expiresAt: string) => {
    const now = new Date()
    const expires = new Date(expiresAt)
    const diff = expires.getTime() - now.getTime()

    if (diff <= 0) return 'Expiree'

    const hours = Math.floor(diff / (1000 * 60 * 60))
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))

    if (hours > 0) return `${hours}h ${minutes}m`
    return `${minutes}m`
  }

  // URL de l'image
  const getCardImageUrl = (fileId: string | null | undefined) => {
    if (!fileId) return null
    return `${API_URL}/api/cards/image/${fileId}`
  }

  // Nombre total de demandes en attente
  const pendingReceivedCount = myRequests?.received?.length || 0
  const pendingSentCount = myRequests?.sent?.length || 0

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 bg-gradient-to-br from-accent to-orange-600 rounded-lg flex items-center justify-center">
            <Store className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-display font-bold text-white">Bazaar</h1>
            <p className="text-gray-400">Recherchez et echangez des cartes avec d'autres joueurs</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        <button
          onClick={() => setActiveTab('bazaar')}
          className={`btn flex items-center gap-2 ${activeTab === 'bazaar'
              ? 'bg-gradient-to-r from-primary to-secondary text-white'
              : 'bg-dark-700 text-gray-300 hover:bg-dark-600'
            }`}
        >
          <Search className="w-4 h-4" />
          Rechercher
        </button>
        <button
          onClick={() => setActiveTab('requests')}
          className={`btn flex items-center gap-2 relative ${activeTab === 'requests'
              ? 'bg-gradient-to-r from-primary to-secondary text-white'
              : 'bg-dark-700 text-gray-300 hover:bg-dark-600'
            }`}
        >
          <Inbox className="w-4 h-4" />
          Mes demandes
          {pendingReceivedCount > 0 && (
            <span className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full text-xs flex items-center justify-center text-white font-bold">
              {pendingReceivedCount}
            </span>
          )}
        </button>
      </div>

      <AnimatePresence mode="wait">
        {activeTab === 'bazaar' ? (
          <motion.div
            key="bazaar"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
          >
            {/* Barre de recherche */}
            <div className="card mb-6">
              <div className="flex flex-col lg:flex-row gap-4">
                {/* Recherche textuelle */}
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Rechercher une carte..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="input pl-10 w-full"
                  />
                </div>

                {/* Filtre categorie */}
                <div className="relative">
                  <button
                    onClick={() => setShowCategoryDropdown(!showCategoryDropdown)}
                    className="btn bg-dark-700 text-gray-300 flex items-center gap-2 min-w-[180px] justify-between"
                  >
                    <span className="flex items-center gap-2">
                      <Filter className="w-4 h-4" />
                      {selectedCategory || 'Toutes categories'}
                    </span>
                    <ChevronDown className={`w-4 h-4 transition-transform ${showCategoryDropdown ? 'rotate-180' : ''}`} />
                  </button>

                  {showCategoryDropdown && (
                    <div className="absolute z-50 mt-2 w-full bg-dark-800 border border-dark-600 rounded-lg shadow-xl overflow-hidden">
                      <button
                        onClick={() => {
                          setSelectedCategory('')
                          setShowCategoryDropdown(false)
                        }}
                        className={`w-full px-4 py-2 text-left hover:bg-dark-700 ${!selectedCategory ? 'bg-primary/20 text-primary' : 'text-gray-300'
                          }`}
                      >
                        Toutes categories
                      </button>
                      {ALL_CATEGORIES.map((cat) => (
                        <button
                          key={cat}
                          onClick={() => {
                            setSelectedCategory(cat)
                            setShowCategoryDropdown(false)
                          }}
                          className={`w-full px-4 py-2 text-left hover:bg-dark-700 ${selectedCategory === cat ? 'bg-primary/20 text-primary' : 'text-gray-300'
                            }`}
                        >
                          {cat}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Option doublons */}
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeNonDuplicates}
                    onChange={(e) => setIncludeNonDuplicates(e.target.checked)}
                    className="w-4 h-4 rounded bg-dark-700 border-dark-500 text-primary focus:ring-primary"
                  />
                  <span className="text-sm text-gray-400">Afficher sans doublon</span>
                </label>

                {/* Bouton refresh */}
                <button
                  onClick={() => refetchSearch()}
                  className="btn bg-dark-700 text-gray-300 hover:bg-dark-600"
                  disabled={searchLoading}
                >
                  <RefreshCw className={`w-4 h-4 ${searchLoading ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            {/* Resultats */}
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-display font-bold text-white flex items-center gap-2">
                  <Store className="w-5 h-5 text-primary" />
                  Cartes disponibles
                </h2>
                <span className="text-sm text-gray-400">
                  {searchResults?.total || 0} carte(s) trouvee(s)
                </span>
              </div>

              {searchError ? (
                <div className="text-center py-12">
                  <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
                  <p className="text-red-400">Erreur lors de la recherche</p>
                  <p className="text-sm text-gray-500 mt-2">
                    {(searchError as any)?.message || 'Erreur inconnue'}
                  </p>
                  <button
                    onClick={() => refetchSearch()}
                    className="btn btn-secondary mt-4"
                  >
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Reessayer
                  </button>
                </div>
              ) : searchLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="w-8 h-8 text-primary animate-spin" />
                </div>
              ) : searchResults?.cards && searchResults.cards.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {searchResults.cards.map((card) => {
                    const colors = CATEGORY_COLORS[card.category as keyof typeof CATEGORY_COLORS]
                    const imageUrl = getCardImageUrl(card.file_id)

                    return (
                      <div
                        key={`${card.category}-${card.name}`}
                        className="card bg-dark-700 hover:bg-dark-600 transition-all border border-dark-600 hover:border-primary/50 overflow-hidden"
                      >
                        {/* Image de la carte */}
                        {imageUrl && (
                          <div className="relative h-40 -mx-4 -mt-4 mb-4 overflow-hidden bg-dark-800">
                            <img
                              src={imageUrl}
                              alt={card.name}
                              className="w-full h-full object-cover opacity-80"
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-dark-700 to-transparent" />
                          </div>
                        )}

                        <div className="flex items-start justify-between mb-2">
                          <span className={`text-xs font-bold ${colors?.text || 'text-gray-400'}`}>
                            {card.category}
                          </span>
                          <span className="text-xs text-green-400 font-medium">
                            {card.total_available} dispo
                          </span>
                        </div>

                        <p className="text-lg text-white font-medium mb-3">
                          {card.name.replace('.png', '')}
                        </p>

                        {/* Liste des proprietaires */}
                        <div className="space-y-2">
                          {card.owners.slice(0, 3).map((owner) => (
                            <div
                              key={owner.user_id}
                              className="flex items-center justify-between p-2 bg-dark-800 rounded-lg"
                            >
                              <div className="flex items-center gap-2">
                                <User className="w-4 h-4 text-gray-500" />
                                <span className="text-sm text-gray-300 truncate max-w-[120px]">
                                  {owner.username}
                                </span>
                              </div>
                              <button
                                onClick={() => {
                                  setSelectedCard(card)
                                  setSelectedOwner(owner)
                                  setShowTradeModal(true)
                                }}
                                className="btn bg-primary/20 hover:bg-primary/40 text-primary text-xs px-3 py-1"
                              >
                                Echanger
                              </button>
                            </div>
                          ))}
                          {card.owners.length > 3 && (
                            <p className="text-xs text-gray-500 text-center">
                              +{card.owners.length - 3} autre(s) proprietaire(s)
                            </p>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="text-center py-12">
                  <Store className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                  <p className="text-gray-400">Aucune carte trouvee</p>
                  <p className="text-sm text-gray-500 mt-2">
                    Essayez de modifier vos filtres de recherche
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="requests"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            {/* Demandes recues */}
            <div className="card mb-6">
              <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
                <Inbox className="w-5 h-5 text-green-400" />
                Demandes recues
                {pendingReceivedCount > 0 && (
                  <span className="bg-green-500/20 text-green-400 text-sm px-2 py-1 rounded-full">
                    {pendingReceivedCount} en attente
                  </span>
                )}
              </h2>

              {requestsLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 text-primary animate-spin" />
                </div>
              ) : myRequests?.received && myRequests.received.length > 0 ? (
                <div className="space-y-4">
                  {myRequests.received.map((request) => (
                    <div
                      key={request.id}
                      className="p-4 bg-dark-700 rounded-lg border border-green-500/30"
                    >
                      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                        <div className="flex items-center gap-4">
                          <div className="text-center">
                            <p className="text-xs text-gray-400">Vous recevez</p>
                            <p className={`font-bold ${CATEGORY_COLORS[request.offered_card.category as keyof typeof CATEGORY_COLORS]?.text || 'text-white'}`}>
                              {request.offered_card.name.replace('.png', '')}
                            </p>
                            <p className="text-xs text-gray-500">{request.offered_card.category}</p>
                          </div>

                          <ArrowLeftRight className="w-6 h-6 text-gray-500" />

                          <div className="text-center">
                            <p className="text-xs text-gray-400">Vous donnez</p>
                            <p className={`font-bold ${CATEGORY_COLORS[request.requested_card.category as keyof typeof CATEGORY_COLORS]?.text || 'text-white'}`}>
                              {request.requested_card.name.replace('.png', '')}
                            </p>
                            <p className="text-xs text-gray-500">{request.requested_card.category}</p>
                          </div>
                        </div>

                        <div className="flex items-center gap-4">
                          <div className="text-right">
                            <p className="text-sm text-gray-400">
                              De: <span className="text-white">{request.requester_name}</span>
                            </p>
                            <p className="text-xs text-yellow-400 flex items-center gap-1 justify-end">
                              <Clock className="w-3 h-3" />
                              Expire dans {formatTimeRemaining(request.expires_at)}
                            </p>
                          </div>

                          <div className="flex gap-2">
                            <button
                              onClick={() => acceptMutation.mutate(request.id)}
                              disabled={acceptMutation.isPending}
                              className="btn bg-green-500/20 hover:bg-green-500/40 text-green-400"
                            >
                              {acceptMutation.isPending ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <Check className="w-4 h-4" />
                              )}
                            </button>
                            <button
                              onClick={() => declineMutation.mutate(request.id)}
                              disabled={declineMutation.isPending}
                              className="btn bg-red-500/20 hover:bg-red-500/40 text-red-400"
                            >
                              {declineMutation.isPending ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <X className="w-4 h-4" />
                              )}
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <Inbox className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                  <p className="text-gray-400">Aucune demande recue</p>
                </div>
              )}
            </div>

            {/* Demandes envoyees */}
            <div className="card">
              <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
                <Send className="w-5 h-5 text-blue-400" />
                Demandes envoyees
                {pendingSentCount > 0 && (
                  <span className="bg-blue-500/20 text-blue-400 text-sm px-2 py-1 rounded-full">
                    {pendingSentCount} en attente
                  </span>
                )}
              </h2>

              {requestsLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 text-primary animate-spin" />
                </div>
              ) : myRequests?.sent && myRequests.sent.length > 0 ? (
                <div className="space-y-4">
                  {myRequests.sent.map((request) => (
                    <div
                      key={request.id}
                      className="p-4 bg-dark-700 rounded-lg border border-blue-500/30"
                    >
                      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                        <div className="flex items-center gap-4">
                          <div className="text-center">
                            <p className="text-xs text-gray-400">Vous donnez</p>
                            <p className={`font-bold ${CATEGORY_COLORS[request.offered_card.category as keyof typeof CATEGORY_COLORS]?.text || 'text-white'}`}>
                              {request.offered_card.name.replace('.png', '')}
                            </p>
                            <p className="text-xs text-gray-500">{request.offered_card.category}</p>
                          </div>

                          <ArrowLeftRight className="w-6 h-6 text-gray-500" />

                          <div className="text-center">
                            <p className="text-xs text-gray-400">Vous recevez</p>
                            <p className={`font-bold ${CATEGORY_COLORS[request.requested_card.category as keyof typeof CATEGORY_COLORS]?.text || 'text-white'}`}>
                              {request.requested_card.name.replace('.png', '')}
                            </p>
                            <p className="text-xs text-gray-500">{request.requested_card.category}</p>
                          </div>
                        </div>

                        <div className="flex items-center gap-4">
                          <div className="text-right">
                            <p className="text-sm text-gray-400">
                              A: <span className="text-white">{request.target_name}</span>
                            </p>
                            <p className="text-xs text-yellow-400 flex items-center gap-1 justify-end">
                              <Clock className="w-3 h-3" />
                              Expire dans {formatTimeRemaining(request.expires_at)}
                            </p>
                          </div>

                          <button
                            onClick={() => cancelMutation.mutate(request.id)}
                            disabled={cancelMutation.isPending}
                            className="btn bg-red-500/20 hover:bg-red-500/40 text-red-400"
                          >
                            {cancelMutation.isPending ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <X className="w-4 h-4" />
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <Send className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                  <p className="text-gray-400">Aucune demande envoyee</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Modal de proposition d'echange */}
      <AnimatePresence>
        {showTradeModal && selectedCard && selectedOwner && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
            onClick={() => {
              setShowTradeModal(false)
              setMyCardToOffer(null)
            }}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-dark-800 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-xl font-display font-bold text-white">
                    Proposer un echange
                  </h3>
                  <button
                    onClick={() => {
                      setShowTradeModal(false)
                      setMyCardToOffer(null)
                    }}
                    className="text-gray-400 hover:text-white"
                  >
                    <X className="w-6 h-6" />
                  </button>
                </div>

                {/* Carte demandee */}
                <div className="mb-6">
                  <p className="text-sm text-gray-400 mb-2">Vous demandez:</p>
                  <div className="p-4 bg-dark-700 rounded-lg">
                    <div className="flex items-center gap-4">
                      {selectedCard.file_id && (
                        <img
                          src={getCardImageUrl(selectedCard.file_id)!}
                          alt={selectedCard.name}
                          className="w-20 h-28 object-cover rounded-lg"
                        />
                      )}
                      <div>
                        <p className={`text-sm font-bold ${CATEGORY_COLORS[selectedCard.category as keyof typeof CATEGORY_COLORS]?.text || 'text-gray-400'}`}>
                          {selectedCard.category}
                        </p>
                        <p className="text-xl text-white font-medium">
                          {selectedCard.name.replace('.png', '')}
                        </p>
                        <p className="text-sm text-gray-400">
                          Proprietaire: {selectedOwner.username}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Carte a offrir */}
                <div className="mb-6">
                  <p className="text-sm text-gray-400 mb-2">Choisissez une carte a offrir:</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 max-h-60 overflow-y-auto p-2">
                    {eligibleCards.map((card, index) => {
                      const colors = CATEGORY_COLORS[card.category as keyof typeof CATEGORY_COLORS]
                      const isSelected = myCardToOffer?.category === card.category &&
                        myCardToOffer?.name === card.name

                      return (
                        <button
                          key={`${card.category}-${card.name}-${index}`}
                          onClick={() => setMyCardToOffer(card)}
                          className={`p-3 rounded-lg text-left transition-all ${isSelected
                              ? 'bg-accent/30 border-2 border-accent'
                              : 'bg-dark-700 border-2 border-transparent hover:border-primary/50'
                            }`}
                        >
                          <p className={`text-xs font-bold ${colors?.text || 'text-gray-400'}`}>
                            {card.category}
                          </p>
                          <p className="text-sm text-white truncate">
                            {card.name.replace('.png', '')}
                          </p>
                          <p className="text-xs text-gray-500">x{card.count}</p>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Resume et confirmation */}
                {myCardToOffer && (
                  <div className="p-4 bg-primary/10 rounded-lg mb-6">
                    <p className="text-sm text-gray-300 text-center">
                      Vous proposez <span className="text-white font-bold">{myCardToOffer.name.replace('.png', '')}</span>
                      {' '}contre <span className="text-white font-bold">{selectedCard.name.replace('.png', '')}</span>
                    </p>
                  </div>
                )}

                {/* Boutons */}
                <div className="flex gap-4">
                  <button
                    onClick={() => {
                      setShowTradeModal(false)
                      setMyCardToOffer(null)
                    }}
                    className="btn bg-dark-700 text-gray-300 flex-1"
                  >
                    Annuler
                  </button>
                  <button
                    onClick={() => {
                      if (!myCardToOffer) {
                        toast.error('Selectionnez une carte a offrir')
                        return
                      }
                      proposeMutation.mutate({
                        target_id: selectedOwner.user_id,
                        offered_category: myCardToOffer.category,
                        offered_name: myCardToOffer.name,
                        requested_category: selectedCard.category,
                        requested_name: selectedCard.name,
                      })
                    }}
                    disabled={!myCardToOffer || proposeMutation.isPending}
                    className="btn btn-primary flex-1 flex items-center justify-center gap-2"
                  >
                    {proposeMutation.isPending ? (
                      <Loader2 className="w-5 h-5 animate-spin" />
                    ) : (
                      <>
                        <Send className="w-5 h-5" />
                        Envoyer la demande
                      </>
                    )}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
