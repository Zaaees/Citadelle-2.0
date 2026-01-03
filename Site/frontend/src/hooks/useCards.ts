import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import type { Card, CategoryInfo, CardCategory } from '../types/card'
import { useAuthStore } from '../stores/authStore'

/**
 * Hook pour récupérer toutes les cartes
 */
export function useCards(category?: CardCategory) {
  const query = useQuery({
    queryKey: ['cards', category],
    queryFn: async () => {
      console.log('[useCards] Fetching cards...', { category })
      try {
        const params = category ? { category } : {}
        const response = await api.get<Card[]>('/api/cards/catalog', { params })
        console.log('[useCards] Cards fetched successfully:', response.data?.length, 'cards')
        return response.data
      } catch (error) {
        console.error('[useCards] Error fetching cards:', error)
        throw error
      }
    },
    staleTime: 5 * 60 * 1000, // 5 minutes (cohérent avec CACHE_VALIDITY_DURATION du bot)
    retry: 2, // Retry 2 fois en cas d'erreur
  })

  console.log('[useCards] Query state:', {
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    dataLength: query.data?.length
  })

  return query
}

/**
 * Hook pour récupérer les informations sur les catégories
 */
export function useCategoriesInfo() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: async () => {
      const response = await api.get<CategoryInfo[]>('/api/cards/categories')
      return response.data
    },
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Hook pour récupérer la collection de l'utilisateur
 */
export function useUserCollection() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)

  return useQuery({
    queryKey: ['user', 'collection'],
    queryFn: async () => {
      const response = await api.get<{
        cards: Array<{ category: string; name: string; count: number; acquired_date?: string }>
        total_cards: number
        unique_cards: number
        completion_percentage: number
      }>('/api/cards/inventory')
      return response.data
    },
    enabled: isAuthenticated, // N'exécuter que si l'utilisateur est authentifié
    staleTime: 2 * 60 * 1000, // 2 minutes (plus court car collection change souvent)
    retry: 1, // Retry une seule fois en cas d'erreur
  })
}
