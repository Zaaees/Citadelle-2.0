import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Dices, Sparkles, Gift, Flame, Loader2, Check, X } from 'lucide-react'
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

interface DrawResult {
  success: boolean
  message: string
  cards: DrawnCard[]
}

export default function Draw() {
  const queryClient = useQueryClient()
  const [drawnCards, setDrawnCards] = useState<DrawnCard[]>([])
  const [isRevealing, setIsRevealing] = useState(false)
  const [revealedCount, setRevealedCount] = useState(0)
  const [selectedSacrificial, setSelectedSacrificial] = useState<Set<string>>(new Set())

  // Récupérer le statut des tirages
  const { data: drawStatus, isLoading: statusLoading } = useQuery({
    queryKey: ['draw', 'status'],
    queryFn: async () => {
      const response = await api.get<DrawStatus>('/api/draw/status')
      return response.data
    },
    refetchInterval: 30000, // Rafraîchir toutes les 30 secondes
  })

  // Mutation pour le tirage journalier
  const dailyDrawMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<DrawResult>('/api/draw/daily')
      return response.data
    },
    onSuccess: (data) => {
      setDrawnCards(data.cards)
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
      setDrawnCards(data.cards)
      setIsRevealing(true)
      setRevealedCount(0)
      queryClient.invalidateQueries({ queryKey: ['draw', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['user', 'collection'] })
      toast.success(data.message)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Erreur lors du tirage bonus')
    },
  })

  // Mutation pour le tirage sacrificiel
  const sacrificialDrawMutation = useMutation({
    mutationFn: async (cards: Array<{ category: string; name: string }>) => {
      const response = await api.post<DrawResult>('/api/draw/sacrificial', cards)
      return response.data
    },
    onSuccess: (data) => {
      setDrawnCards(data.cards)
      setIsRevealing(true)
      setRevealedCount(0)
      setSelectedSacrificial(new Set())
      queryClient.invalidateQueries({ queryKey: ['draw', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['user', 'collection'] })
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

  // Toggle sélection carte sacrificielle
  const toggleSacrificialCard = (category: string, name: string) => {
    const key = `${category}:${name}`
    const newSelected = new Set(selectedSacrificial)
    if (newSelected.has(key)) {
      newSelected.delete(key)
    } else if (newSelected.size < 5) {
      newSelected.add(key)
    }
    setSelectedSacrificial(newSelected)
  }

  // Effectuer le tirage sacrificiel
  const performSacrificialDraw = () => {
    if (selectedSacrificial.size !== 5) {
      toast.error('Sélectionnez exactement 5 cartes à sacrifier')
      return
    }

    const cards = Array.from(selectedSacrificial).map((key) => {
      const [category, name] = key.split(':')
      return { category, name }
    })

    sacrificialDrawMutation.mutate(cards)
  }

  const isDrawing = dailyDrawMutation.isPending || bonusDrawMutation.isPending || sacrificialDrawMutation.isPending

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
              {isRevealing ? '( Révélation en cours...' : '<‰ Vos nouvelles cartes !'}
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
                onClick={() => {
                  // Ouvrir le modal de sélection
                  document.getElementById('sacrificial-modal')?.classList.remove('hidden')
                }}
                disabled={isDrawing}
                className="btn btn-secondary w-full"
              >
                <Flame className="w-5 h-5 mr-2" />
                Sélectionner les cartes
              </button>
            ) : (
              <div className="text-center">
                <p className="text-gray-400 text-sm">
                  {!drawStatus?.can_sacrificial_draw
                    ? 'Déjà effectué aujourd\'hui'
                    : 'Pas assez de cartes éligibles'}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal de sélection sacrificielle */}
      <div id="sacrificial-modal" className="hidden fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
        <div className="card max-w-2xl w-full max-h-[80vh] overflow-y-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-display font-bold text-white">
              <Flame className="w-6 h-6 inline mr-2 text-secondary" />
              Sélectionnez 5 cartes à sacrifier
            </h2>
            <button
              onClick={() => {
                document.getElementById('sacrificial-modal')?.classList.add('hidden')
                setSelectedSacrificial(new Set())
              }}
              className="text-gray-400 hover:text-white"
            >
              <X className="w-6 h-6" />
            </button>
          </div>

          <p className="text-gray-400 text-sm mb-4">
            Cartes sélectionnées : {selectedSacrificial.size}/5
          </p>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
            {drawStatus?.sacrificial_cards?.map((card, index) => {
              const key = `${card.category}:${card.name}`
              const isSelected = selectedSacrificial.has(key)

              return (
                <button
                  key={`${key}-${index}`}
                  onClick={() => toggleSacrificialCard(card.category, card.name)}
                  className={`
                    p-3 rounded-lg border-2 text-left transition-all
                    ${isSelected
                      ? 'border-secondary bg-secondary/20'
                      : 'border-dark-600 bg-dark-700 hover:border-dark-500'
                    }
                  `}
                >
                  <p className="text-xs text-gray-400">{card.category}</p>
                  <p className="text-sm text-white font-medium truncate">
                    {card.name.replace('.png', '')}
                  </p>
                  {isSelected && (
                    <Check className="w-4 h-4 text-secondary mt-1" />
                  )}
                </button>
              )
            })}
          </div>

          <button
            onClick={performSacrificialDraw}
            disabled={selectedSacrificial.size !== 5 || sacrificialDrawMutation.isPending}
            className={`
              btn w-full
              ${selectedSacrificial.size === 5
                ? 'btn-secondary'
                : 'bg-dark-600 text-gray-500 cursor-not-allowed'
              }
            `}
          >
            {sacrificialDrawMutation.isPending ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <>
                <Flame className="w-5 h-5 mr-2" />
                Sacrifier et tirer ({selectedSacrificial.size}/5)
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
