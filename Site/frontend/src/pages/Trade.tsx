import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Repeat2, Package, ArrowRight, Plus, Minus,
  Loader2, X, Check, Clock, AlertCircle, Users, Eye, Trash2, User
} from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../services/api'
import { CATEGORY_COLORS } from '../types/card'
import { useAuthStore } from '../stores/authStore'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface VaultCard {
  category: string
  name: string
  count: number
}

interface UserVault {
  user_id: string
  cards: VaultCard[]
  total_cards: number
}

interface WeeklyTradeLimit {
  used: number
  remaining: number
  limit: number
  can_trade: boolean
}

interface InventoryCard {
  category: string
  name: string
  count: number
  is_full: boolean
  file_id: string | null
}

interface BoardOffer {
  id: number
  owner_id: number
  owner_name: string | null
  category: string
  name: string
  comment: string | null
  timestamp: string
}

export default function Trade() {
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const currentUserId = user?.user_id
  const [activeTab, setActiveTab] = useState<'board' | 'vault' | 'inventory'>('board')
  const [selectedForVault, setSelectedForVault] = useState<string | null>(null)

  // Recuperer le tableau d'echanges
  const { data: boardOffers, isLoading: boardLoading } = useQuery({
    queryKey: ['trade', 'board'],
    queryFn: async () => {
      const response = await api.get<BoardOffer[]>('/api/trade/board')
      return response.data
    },
  })

  // Recuperer le coffre de l'utilisateur
  const { data: vault, isLoading: vaultLoading } = useQuery({
    queryKey: ['vault'],
    queryFn: async () => {
      const response = await api.get<UserVault>('/api/user/vault')
      return response.data
    },
  })

  // Recuperer le statut des echanges hebdomadaires
  const { data: tradeLimit, isLoading: statusLoading } = useQuery({
    queryKey: ['trade', 'weekly-limit'],
    queryFn: async () => {
      const response = await api.get<WeeklyTradeLimit>('/api/trade/weekly-limit')
      return response.data
    },
  })

  // Recuperer l'inventaire pour le depot
  const { data: inventory, isLoading: inventoryLoading } = useQuery({
    queryKey: ['user', 'collection'],
    queryFn: async () => {
      const response = await api.get<{ cards: InventoryCard[] }>('/api/user/collection')
      return response.data
    },
  })

  // Mutation pour deposer une carte dans le coffre
  const depositMutation = useMutation({
    mutationFn: async ({ category, name }: { category: string; name: string }) => {
      const response = await api.post('/api/vault/deposit', null, {
        params: { category, name },
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Carte deposee dans le coffre !')
      queryClient.invalidateQueries({ queryKey: ['vault'] })
      queryClient.invalidateQueries({ queryKey: ['user', 'collection'] })
      setSelectedForVault(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Erreur lors du depot')
    },
  })

  // Mutation pour retirer une carte du coffre
  const withdrawMutation = useMutation({
    mutationFn: async ({ category, name }: { category: string; name: string }) => {
      const response = await api.post('/api/vault/withdraw', null, {
        params: { category, name },
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Carte retiree du coffre !')
      queryClient.invalidateQueries({ queryKey: ['vault'] })
      queryClient.invalidateQueries({ queryKey: ['user', 'collection'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Erreur lors du retrait')
    },
  })

  // Filtrer les cartes eligibles au depot (pas de Full)
  const eligibleForDeposit = inventory?.cards?.filter(
    (card) => !card.is_full && card.count > 0
  ) || []

  // Formater la date
  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr)
      return date.toLocaleDateString('fr-FR', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return dateStr
    }
  }

  // Construire l'URL de l'image de carte
  const getCardImageUrl = (fileId: string | null) => {
    if (!fileId) return null
    return `${API_URL}/api/cards/image/${fileId}`
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 bg-gradient-to-br from-accent to-orange-600 rounded-lg flex items-center justify-center">
            <Repeat2 className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-display font-bold text-white">Systeme d'echanges</h1>
            <p className="text-gray-400">Consultez le tableau d'echanges et gerez votre coffre</p>
          </div>
        </div>

        {/* Statut des echanges */}
        <div className="card bg-gradient-to-r from-dark-800 to-dark-900">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-6">
              <div>
                <p className="text-sm text-gray-400">Echanges cette semaine</p>
                <p className="text-2xl font-bold text-white">
                  {statusLoading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    `${tradeLimit?.used || 0}/3`
                  )}
                </p>
              </div>
              <div className="h-12 w-px bg-dark-600" />
              <div>
                <p className="text-sm text-gray-400">Echanges restants</p>
                <p className={`text-2xl font-bold ${
                  (tradeLimit?.remaining || 0) > 0 ? 'text-green-400' : 'text-red-400'
                }`}>
                  {tradeLimit?.remaining ?? 3}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <Clock className="w-4 h-4" />
              <span>Reset chaque lundi</span>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        <button
          onClick={() => setActiveTab('board')}
          className={`
            btn flex items-center gap-2
            ${activeTab === 'board'
              ? 'bg-gradient-to-r from-primary to-secondary text-white'
              : 'bg-dark-700 text-gray-300 hover:bg-dark-600'
            }
          `}
        >
          <Users className="w-4 h-4" />
          Tableau d'echanges ({boardOffers?.length || 0})
        </button>
        <button
          onClick={() => setActiveTab('vault')}
          className={`
            btn flex items-center gap-2
            ${activeTab === 'vault'
              ? 'bg-gradient-to-r from-primary to-secondary text-white'
              : 'bg-dark-700 text-gray-300 hover:bg-dark-600'
            }
          `}
        >
          <Package className="w-4 h-4" />
          Mon Coffre ({vault?.total_cards || 0})
        </button>
        <button
          onClick={() => setActiveTab('inventory')}
          className={`
            btn flex items-center gap-2
            ${activeTab === 'inventory'
              ? 'bg-gradient-to-r from-primary to-secondary text-white'
              : 'bg-dark-700 text-gray-300 hover:bg-dark-600'
            }
          `}
        >
          <Plus className="w-4 h-4" />
          Deposer des cartes
        </button>
      </div>

      {/* Contenu */}
      <AnimatePresence mode="wait">
        {activeTab === 'board' ? (
          <motion.div
            key="board"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
          >
            {/* Mes offres */}
            {boardOffers && boardOffers.filter(o => currentUserId && o.owner_id === currentUserId).length > 0 && (
              <div className="card mb-6 border-2 border-accent/50">
                <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
                  <User className="w-5 h-5 text-accent" />
                  Mes offres sur le tableau
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                  {boardOffers.filter(o => currentUserId && o.owner_id === currentUserId).map((offer) => {
                    const colors = CATEGORY_COLORS[offer.category as keyof typeof CATEGORY_COLORS]
                    return (
                      <div
                        key={offer.id}
                        className="card bg-accent/10 border-2 border-accent/30 hover:border-accent transition-colors"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <span className={`text-xs font-bold ${colors?.text || 'text-gray-400'}`}>
                            {offer.category}
                          </span>
                          <span className="text-xs text-accent font-bold">
                            Mon offre #{offer.id}
                          </span>
                        </div>

                        <p className="text-lg text-white font-medium mb-2">
                          {offer.name}
                        </p>

                        {offer.comment && (
                          <p className="text-sm text-gray-400 italic mb-3 line-clamp-2">
                            "{offer.comment}"
                          </p>
                        )}

                        <div className="border-t border-accent/20 pt-3 mt-auto">
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-gray-500">
                              {formatDate(offer.timestamp)}
                            </span>
                            <button
                              className="btn bg-red-500/20 hover:bg-red-500/40 text-red-400 text-xs px-3 py-1 flex items-center gap-1"
                              onClick={() => toast('Utilisez le bot Discord pour retirer votre offre', { icon: 'info' })}
                            >
                              <Trash2 className="w-3 h-3" />
                              Retirer
                            </button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Offres des autres joueurs */}
            <div className="card">
              <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
                <Users className="w-5 h-5 text-primary" />
                Offres des autres joueurs
              </h2>

              {boardLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="w-8 h-8 text-primary animate-spin" />
                </div>
              ) : boardOffers && boardOffers.filter(o => !currentUserId || o.owner_id !== currentUserId).length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                  {boardOffers.filter(o => !currentUserId || o.owner_id !== currentUserId).map((offer) => {
                    const colors = CATEGORY_COLORS[offer.category as keyof typeof CATEGORY_COLORS]
                    return (
                      <div
                        key={offer.id}
                        className="card bg-dark-700 hover:bg-dark-600 transition-colors border border-dark-600 hover:border-primary/50"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <span className={`text-xs font-bold ${colors?.text || 'text-gray-400'}`}>
                            {offer.category}
                          </span>
                          <span className="text-xs text-gray-500">
                            #{offer.id}
                          </span>
                        </div>

                        <p className="text-lg text-white font-medium mb-2">
                          {offer.name}
                        </p>

                        {offer.comment && (
                          <p className="text-sm text-gray-400 italic mb-3 line-clamp-2">
                            "{offer.comment}"
                          </p>
                        )}

                        <div className="border-t border-dark-500 pt-3 mt-auto">
                          <div className="flex items-center justify-between">
                            <div className="text-xs text-gray-500">
                              <span className="text-gray-400">
                                {offer.owner_name || `Joueur #${offer.owner_id.toString().slice(-4)}`}
                              </span>
                              <br />
                              {formatDate(offer.timestamp)}
                            </div>
                            <button
                              className="btn bg-primary/20 hover:bg-primary/40 text-primary text-xs px-3 py-1 flex items-center gap-1"
                              onClick={() => toast('Utilisez le bot Discord pour proposer un echange', { icon: 'info' })}
                            >
                              <Eye className="w-3 h-3" />
                              Details
                            </button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="text-center py-12">
                  <Users className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                  <p className="text-gray-400">Aucune offre des autres joueurs</p>
                  <p className="text-sm text-gray-500 mt-2">
                    Le tableau d'echanges est vide pour le moment
                  </p>
                </div>
              )}
            </div>

            {/* Info sur le tableau */}
            <div className="card mt-6 bg-gradient-to-br from-primary/10 to-secondary/10 border-primary/30">
              <h3 className="text-lg font-display font-bold text-white mb-2 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-primary" />
                Comment fonctionne le tableau d'echanges ?
              </h3>
              <ul className="text-sm text-gray-300 space-y-2">
                <li>- Consultez les cartes proposees par les autres joueurs</li>
                <li>- Deposez vos cartes via le bot Discord avec /echange deposer</li>
                <li>- Proposez un echange via le bot Discord</li>
                <li>- Maximum 3 echanges par semaine (reset le lundi)</li>
              </ul>
            </div>
          </motion.div>
        ) : activeTab === 'vault' ? (
          <motion.div
            key="vault"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
          >
            <div className="card">
              <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
                <Package className="w-5 h-5 text-primary" />
                Contenu du coffre
              </h2>

              {vaultLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="w-8 h-8 text-primary animate-spin" />
                </div>
              ) : vault?.cards && vault.cards.length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                  {vault.cards.map((card, index) => {
                    const colors = CATEGORY_COLORS[card.category as keyof typeof CATEGORY_COLORS]
                    return (
                      <div
                        key={`${card.category}-${card.name}-${index}`}
                        className="card bg-dark-700 hover:bg-dark-600 transition-colors group"
                      >
                        <div className={`text-xs font-bold mb-2 ${colors?.text || 'text-gray-400'}`}>
                          {card.category}
                        </div>
                        <p className="text-sm text-white font-medium mb-3 truncate">
                          {card.name.replace('.png', '')}
                        </p>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-gray-400">x{card.count}</span>
                          <button
                            onClick={() => withdrawMutation.mutate({
                              category: card.category,
                              name: card.name
                            })}
                            disabled={withdrawMutation.isPending}
                            className="btn bg-red-500/20 hover:bg-red-500/40 text-red-400 text-xs px-2 py-1"
                          >
                            {withdrawMutation.isPending ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <Minus className="w-3 h-3" />
                            )}
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="text-center py-12">
                  <Package className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                  <p className="text-gray-400">Votre coffre est vide</p>
                  <p className="text-sm text-gray-500 mt-2">
                    Deposez des cartes pour preparer des echanges
                  </p>
                </div>
              )}
            </div>

            {/* Info sur le coffre */}
            <div className="card mt-6 bg-gradient-to-br from-primary/10 to-secondary/10 border-primary/30">
              <h3 className="text-lg font-display font-bold text-white mb-2 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-primary" />
                Comment fonctionne le coffre ?
              </h3>
              <ul className="text-sm text-gray-300 space-y-2">
                <li>- Deposez des cartes dans votre coffre pour preparer un echange</li>
                <li>- Les cartes Full ne peuvent pas etre deposees</li>
                <li>- Vous pouvez effectuer jusqu'a 3 echanges par semaine</li>
                <li>- Le compteur se reinitialise chaque lundi</li>
              </ul>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="inventory"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <div className="card">
              <h2 className="text-xl font-display font-bold text-white mb-4 flex items-center gap-2">
                <Plus className="w-5 h-5 text-accent" />
                Deposer une carte dans le coffre
              </h2>

              {inventoryLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="w-8 h-8 text-accent animate-spin" />
                </div>
              ) : eligibleForDeposit.length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                  {eligibleForDeposit.map((card, index) => {
                    const colors = CATEGORY_COLORS[card.category as keyof typeof CATEGORY_COLORS]
                    const isSelected = selectedForVault === `${card.category}:${card.name}`

                    return (
                      <button
                        key={`${card.category}-${card.name}-${index}`}
                        onClick={() => setSelectedForVault(
                          isSelected ? null : `${card.category}:${card.name}`
                        )}
                        className={`
                          card text-left transition-all
                          ${isSelected
                            ? 'bg-accent/20 border-accent'
                            : 'bg-dark-700 hover:bg-dark-600 border-dark-600'
                          }
                        `}
                      >
                        <div className={`text-xs font-bold mb-2 ${colors?.text || 'text-gray-400'}`}>
                          {card.category}
                        </div>
                        <p className="text-sm text-white font-medium mb-2 truncate">
                          {card.name.replace('.png', '')}
                        </p>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-gray-400">x{card.count}</span>
                          {isSelected && <Check className="w-4 h-4 text-accent" />}
                        </div>
                      </button>
                    )
                  })}
                </div>
              ) : (
                <div className="text-center py-12">
                  <AlertCircle className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                  <p className="text-gray-400">Aucune carte eligible</p>
                  <p className="text-sm text-gray-500 mt-2">
                    Vous n'avez pas de cartes pouvant etre deposees
                  </p>
                </div>
              )}
            </div>

            {/* Bouton de depot */}
            {selectedForVault && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50"
              >
                <button
                  onClick={() => {
                    const [category, name] = selectedForVault.split(':')
                    depositMutation.mutate({ category, name })
                  }}
                  disabled={depositMutation.isPending}
                  className="btn btn-accent text-lg px-8 py-4 shadow-2xl flex items-center gap-3"
                >
                  {depositMutation.isPending ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <>
                      <ArrowRight className="w-5 h-5" />
                      Deposer dans le coffre
                    </>
                  )}
                </button>
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
