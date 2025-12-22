import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Dices, Sparkles, Gift, Flame, Loader2, Check, X, AlertTriangle, Crown } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../services/api'
import { CATEGORY_COLORS, type CardCategory } from '../types/card'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface DrawStatus {
  can_daily_draw: boolean
  bonus_available: number
  can_sacrificial_draw: boolean
  sacrificial_cards: Array<{ category: string; name: string }>
}

interface DrawnCard {
  category: CardCategory
  name: string
  file_id: string
  is_new_discovery: boolean
  discovery_index: number | null
  is_full: boolean
}

// Interface pour les cartes Full obtenues par upgrade
interface UpgradedCard {
  category: string
  name: string
  file_id: string | null
  original_name: string
  sacrificed_count: number
}

// Nouveau format de réponse des tirages
interface DrawResult {
  drawn_cards: DrawnCard[]
  upgraded_cards: UpgradedCard[]
}

// Interface pour les cartes de preview sacrificiel
interface SacrificialPreviewCard {
  category: string
  name: string
  file_id: string | null
  is_full: boolean
}

export default function Draw() {
  const queryClient = useQueryClient()
  const [drawnCards, setDrawnCards] = useState<DrawnCard[]>([])
  const [isRevealing, setIsRevealing] = useState(false)
  const [revealedCount, setRevealedCount] = useState(0)
  const [showSacrificialModal, setShowSacrificialModal] = useState(false)
  const [upgradedCards, setUpgradedCards] = useState<UpgradedCard[]>([])

  // Récupérer le statut des tirages
  const { data: drawStatus, isLoading: statusLoading } = useQuery({
    queryKey: ['draw', 'status'],
    queryFn: async () => {
      const response = await api.get<DrawStatus>('/api/draw/status')
      return response.data
    },
    refetchInterval: 30000,
  })

  // Récupérer le preview des 5 cartes sacrificielles (pré-sélectionnées par le système)
  const { data: sacrificialPreview, isLoading: previewLoading, refetch: refetchPreview } = useQuery({
    queryKey: ['draw', 'sacrificial', 'preview'],
    queryFn: async () => {
      const response = await api.get<SacrificialPreviewCard[]>('/api/draw/sacrificial/preview')
      return response.data
    },
    enabled: showSacrificialModal && !!drawStatus?.can_sacrificial_draw,
  })

  // Mutation pour le tirage journalier
  const dailyDrawMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<DrawResult>('/api/draw/daily')
      return response.data
    },
    onSuccess: (data) => {
      setDrawnCards(data.drawn_cards)
      setUpgradedCards(data.upgraded_cards)
      setIsRevealing(true)
      setRevealedCount(0)
      queryClient.invalidateQueries({ queryKey: ['draw', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['user', 'collection'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Erreur lors du tirage')
    },
  })

  // Mutation pour le tirage bonus
  const bonusDrawMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<DrawResult>('/api/draw/bonus')
      return response.data
    },
    onSuccess: (data) => {
      setDrawnCards(data.drawn_cards)
      setUpgradedCards(data.upgraded_cards)
      setIsRevealing(true)
      setRevealedCount(0)
      queryClient.invalidateQueries({ queryKey: ['draw', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['user', 'collection'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Erreur lors du tirage bonus')
    },
  })

  // Mutation pour le tirage sacrificiel (pas de paramètres - utilise les cartes pré-sélectionnées)
  const sacrificialDrawMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<DrawResult>('/api/draw/sacrificial')
      return response.data
    },
    onSuccess: (data) => {
      setDrawnCards(data.drawn_cards)
      setUpgradedCards(data.upgraded_cards)
      setIsRevealing(true)
      setRevealedCount(0)
      setShowSacrificialModal(false)
      queryClient.invalidateQueries({ queryKey: ['draw', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['user', 'collection'] })
      queryClient.invalidateQueries({ queryKey: ['draw', 'sacrificial', 'preview'] })
      toast.success('Tirage sacrificiel effectué !')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Erreur lors du tirage sacrificiel')
    },
  })

  // Révéler les cartes une par une
  const revealNextCard = () => {
    if (revealedCount < drawnCards.length) {
      setRevealedCount((prev) => prev + 1)
    } else {
      setIsRevealing(false)
    }
  }

  const isDrawing = dailyDrawMutation.isPending || bonusDrawMutation.isPending || sacrificialDrawMutation.isPending

  // Ouvrir le modal sacrificiel et charger le preview
  const openSacrificialModal = () => {
    setShowSacrificialModal(true)
    refetchPreview()
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 bg-gradient-to-br from-secondary to-pink-600 rounded-lg flex items-center justify-center">
            <Dices className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-display font-bold text-white">Tirages de Cartes</h1>
            <p className="text-gray-400">Obtenez de nouvelles cartes pour votre collection</p>
          </div>
        </div>
      </div>

      {/* Zone de révélation des cartes */}
      <AnimatePresence>
        {drawnCards.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="card mb-8 bg-gradient-to-br from-dark-800 to-dark-900"
          >
            <h2 className="text-xl font-display font-bold text-white mb-6 text-center">
              {isRevealing ? '✨ Révélation en cours...' : '🎉 Vos nouvelles cartes !'}
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
              {drawnCards.map((card, index) => (
                <motion.div
                  key={`${card.category}-${card.name}-${index}`}
                  initial={{ rotateY: 180, opacity: 0 }}
                  animate={{
                    rotateY: index < revealedCount ? 0 : 180,
                    opacity: index < revealedCount ? 1 : 0.3,
                  }}
                  transition={{ duration: 0.6, delay: index * 0.2 }}
                  className="relative"
                  style={{ perspective: '1000px' }}
                >
                  <div
                    className={`
                      card overflow-hidden
                      ${index < revealedCount ? 'border-primary animate-glow' : 'border-dark-600'}
                      ${card.is_new_discovery ? 'ring-2 ring-yellow-400' : ''}
                    `}
                  >
                    {/* Badge nouvelle découverte */}
                    {card.is_new_discovery && index < revealedCount && (
                      <div className="absolute top-2 left-2 z-10 px-2 py-1 rounded-md bg-gradient-to-r from-yellow-600 to-amber-600 border border-yellow-400">
                        <div className="flex items-center gap-1">
                          <Sparkles className="w-3 h-3 text-yellow-100" />
                          <span className="text-xs font-bold text-yellow-100">DÉCOUVERTE #{card.discovery_index}</span>
                        </div>
                      </div>
                    )}

                    {/* Image de la carte */}
                    <div className="aspect-[2/3] bg-gradient-to-br from-dark-700 to-dark-800 rounded-lg overflow-hidden mb-3">
                      {index < revealedCount && card.file_id ? (
                        <img
                          src={`${API_URL}/api/cards/image/${card.file_id}`}
                          alt={card.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <Sparkles className="w-12 h-12 text-primary animate-pulse" />
                        </div>
                      )}
                    </div>

                    {/* Infos carte */}
                    {index < revealedCount && (
                      <div className="text-center">
                        <p className={`text-sm font-bold ${CATEGORY_COLORS[card.category]?.text || 'text-white'}`}>
                          {card.category}
                        </p>
                        <p className="text-white font-medium mt-1">{card.name.replace('.png', '')}</p>
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </div>

            {/* Affichage des cartes Full obtenues par upgrade */}
            {upgradedCards.length > 0 && revealedCount >= drawnCards.length && (
              <div className="mt-6 p-4 bg-gradient-to-r from-amber-900/30 to-yellow-900/30 border-2 border-yellow-500/50 rounded-lg">
                <h3 className="text-lg font-display font-bold text-yellow-400 mb-4 flex items-center gap-2">
                  <Crown className="w-5 h-5" />
                  Cartes Full Obtenues !
                </h3>
                <p className="text-yellow-200/80 text-sm mb-4">
                  Vous avez collecté 5 exemplaires identiques et obtenu ces cartes Full :
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                  {upgradedCards.map((card, index) => (
                    <div
                      key={`upgraded-${index}`}
                      className="bg-dark-800 border-2 border-yellow-500 rounded-lg p-3 text-center animate-pulse"
                    >
                      <div className="w-full aspect-[2/3] bg-gradient-to-br from-yellow-900/50 to-amber-800/50 rounded-md mb-2 flex items-center justify-center overflow-hidden">
                        {card.file_id ? (
                          <img
                            src={`${API_URL}/api/cards/image/${card.file_id}`}
                            alt={card.name}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <Crown className="w-8 h-8 text-yellow-400" />
                        )}
                      </div>
                      <p className="text-yellow-400 text-xs font-medium">{card.category}</p>
                      <p className="text-white font-bold mt-1">{card.name}</p>
                      <p className="text-yellow-300/60 text-xs mt-1">
                        5x {card.original_name} → Full
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Bouton pour révéler */}
            {isRevealing && revealedCount < drawnCards.length ? (
              <button
                onClick={revealNextCard}
                className="btn btn-primary w-full text-lg py-4"
              >
                <Sparkles className="w-5 h-5 mr-2" />
                Révéler la carte suivante ({revealedCount + 1}/{drawnCards.length})
              </button>
            ) : isRevealing ? (
              <button
                onClick={() => {
                  setIsRevealing(false)
                  setDrawnCards([])
                  setUpgradedCards([])
                }}
                className="btn btn-secondary w-full text-lg py-4"
              >
                <Check className="w-5 h-5 mr-2" />
                Terminer
              </button>
            ) : null}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Options de tirage */}
      {!isRevealing && drawnCards.length === 0 && (
        <div className="grid md:grid-cols-3 gap-6">
          {/* Tirage Journalier */}
          <div className="card hover:border-primary transition-colors">
            <div className="w-16 h-16 bg-gradient-to-br from-primary to-purple-600 rounded-xl flex items-center justify-center mx-auto mb-4">
              <Dices className="w-8 h-8 text-white" />
            </div>
            <h3 className="text-xl font-display font-bold text-white text-center mb-2">
              Tirage Journalier
            </h3>
            <p className="text-gray-400 text-center text-sm mb-6">
              Obtenez 3 cartes aléatoires. Disponible une fois par jour.
            </p>

            {statusLoading ? (
              <div className="flex justify-center">
                <Loader2 className="w-6 h-6 text-primary animate-spin" />
              </div>
            ) : drawStatus?.can_daily_draw ? (
              <button
                onClick={() => dailyDrawMutation.mutate()}
                disabled={isDrawing}
                className="btn btn-primary w-full"
              >
                {dailyDrawMutation.isPending ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    <Sparkles className="w-5 h-5 mr-2" />
                    Tirer 3 cartes
                  </>
                )}
              </button>
            ) : (
              <div className="text-center">
                <p className="text-red-400 text-sm mb-2">
                  <X className="w-4 h-4 inline mr-1" />
                  Déjà effectué aujourd'hui
                </p>
                <p className="text-gray-500 text-xs">Revenez demain !</p>
              </div>
            )}
          </div>

          {/* Tirage Bonus */}
          <div className="card hover:border-accent transition-colors">
            <div className="w-16 h-16 bg-gradient-to-br from-accent to-yellow-600 rounded-xl flex items-center justify-center mx-auto mb-4">
              <Gift className="w-8 h-8 text-white" />
            </div>
            <h3 className="text-xl font-display font-bold text-white text-center mb-2">
              Tirage Bonus
            </h3>
            <p className="text-gray-400 text-center text-sm mb-6">
              Utilisez vos tirages bonus accordés par les administrateurs.
            </p>

            {statusLoading ? (
              <div className="flex justify-center">
                <Loader2 className="w-6 h-6 text-accent animate-spin" />
              </div>
            ) : (drawStatus?.bonus_available || 0) > 0 ? (
              <button
                onClick={() => bonusDrawMutation.mutate()}
                disabled={isDrawing}
                className="btn btn-accent w-full"
              >
                {bonusDrawMutation.isPending ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    <Gift className="w-5 h-5 mr-2" />
                    Utiliser un bonus ({drawStatus?.bonus_available})
                  </>
                )}
              </button>
            ) : (
              <div className="text-center">
                <p className="text-gray-400 text-sm">
                  Aucun bonus disponible
                </p>
              </div>
            )}
          </div>

          {/* Tirage Sacrificiel */}
          <div className="card hover:border-secondary transition-colors">
            <div className="w-16 h-16 bg-gradient-to-br from-secondary to-red-600 rounded-xl flex items-center justify-center mx-auto mb-4">
              <Flame className="w-8 h-8 text-white" />
            </div>
            <h3 className="text-xl font-display font-bold text-white text-center mb-2">
              Tirage Sacrificiel
            </h3>
            <p className="text-gray-400 text-center text-sm mb-6">
              Sacrifiez 5 cartes pour en obtenir 3 nouvelles.
            </p>

            {statusLoading ? (
              <div className="flex justify-center">
                <Loader2 className="w-6 h-6 text-secondary animate-spin" />
              </div>
            ) : drawStatus?.can_sacrificial_draw && (drawStatus?.sacrificial_cards?.length || 0) >= 5 ? (
              <button
                onClick={openSacrificialModal}
                disabled={isDrawing}
                className="btn btn-secondary w-full"
              >
                <Flame className="w-5 h-5 mr-2" />
                Voir les cartes à sacrifier
              </button>
            ) : (
              <div className="text-center">
                <p className="text-gray-400 text-sm">
                  {!drawStatus?.can_sacrificial_draw
                    ? 'Déjà effectué aujourd\'hui'
                    : 'Pas assez de cartes éligibles (min. 5)'}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal de confirmation sacrificielle - Affiche les 5 cartes pré-sélectionnées */}
      <AnimatePresence>
        {showSacrificialModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
            onClick={() => setShowSacrificialModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="card max-w-2xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-display font-bold text-white flex items-center gap-2">
                  <Flame className="w-6 h-6 text-secondary" />
                  Tirage Sacrificiel
                </h2>
                <button
                  onClick={() => setShowSacrificialModal(false)}
                  className="text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>

              {/* Warning */}
              <div className="bg-red-900/30 border border-red-700/50 rounded-lg p-4 mb-6">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-red-300 font-medium">Attention !</p>
                    <p className="text-red-400/80 text-sm mt-1">
                      Les 5 cartes suivantes ont été sélectionnées automatiquement pour aujourd'hui.
                      Cette sélection est la même toute la journée. Si vous acceptez, ces cartes seront
                      définitivement retirées de votre collection.
                    </p>
                  </div>
                </div>
              </div>

              {/* Cartes à sacrifier */}
              <div className="mb-6">
                <h3 className="text-sm font-medium text-gray-400 mb-3">
                  Cartes qui seront sacrifiées :
                </h3>

                {previewLoading ? (
                  <div className="flex justify-center py-8">
                    <Loader2 className="w-8 h-8 text-secondary animate-spin" />
                  </div>
                ) : sacrificialPreview && sacrificialPreview.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
                    {sacrificialPreview.map((card, index) => {
                      const colors = CATEGORY_COLORS[card.category as CardCategory]
                      return (
                        <div
                          key={`${card.category}-${card.name}-${index}`}
                          className="bg-dark-700 border-2 border-red-700/50 rounded-lg p-3 text-center"
                        >
                          <div className="w-full aspect-[2/3] bg-gradient-to-br from-dark-600 to-dark-800 rounded-md mb-2 flex items-center justify-center overflow-hidden">
                            {card.file_id ? (
                              <img
                                src={`${API_URL}/api/cards/image/${card.file_id}`}
                                alt={card.name}
                                className="w-full h-full object-cover opacity-75"
                              />
                            ) : (
                              <Flame className="w-8 h-8 text-red-500/50" />
                            )}
                          </div>
                          <p className={`text-xs font-medium ${colors?.text || 'text-gray-400'}`}>
                            {card.category}
                          </p>
                          <p className="text-sm text-white font-medium truncate mt-1">
                            {card.name.replace('.png', '')}
                          </p>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-gray-500 text-center py-4">
                    Impossible de charger les cartes à sacrifier
                  </p>
                )}
              </div>

              {/* Résultat attendu */}
              <div className="bg-dark-700/50 rounded-lg p-4 mb-6">
                <div className="flex items-center justify-center gap-4 text-gray-400">
                  <div className="text-center">
                    <p className="text-2xl font-bold text-red-400">5</p>
                    <p className="text-xs">cartes sacrifiées</p>
                  </div>
                  <Sparkles className="w-6 h-6" />
                  <div className="text-center">
                    <p className="text-2xl font-bold text-green-400">3</p>
                    <p className="text-xs">nouvelles cartes</p>
                  </div>
                </div>
              </div>

              {/* Boutons d'action */}
              <div className="flex gap-3">
                <button
                  onClick={() => setShowSacrificialModal(false)}
                  className="btn bg-dark-600 hover:bg-dark-500 text-white flex-1"
                >
                  <X className="w-5 h-5 mr-2" />
                  Refuser
                </button>
                <button
                  onClick={() => sacrificialDrawMutation.mutate()}
                  disabled={sacrificialDrawMutation.isPending || !sacrificialPreview?.length}
                  className="btn btn-secondary flex-1"
                >
                  {sacrificialDrawMutation.isPending ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <>
                      <Check className="w-5 h-5 mr-2" />
                      Accepter le sacrifice
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
