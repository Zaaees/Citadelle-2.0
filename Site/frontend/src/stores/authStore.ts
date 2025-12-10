import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { User } from '../services/auth'

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: () => boolean
  setAuth: (user: User, token: string) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,

      isAuthenticated: () => {
        const state = get()
        return !!state.token && !!state.user
      },

      setAuth: (user, token) => {
        set({ user, token })
      },

      clearAuth: () => {
        set({ user: null, token: null })
      },
    }),
    {
      name: 'citadelle-auth-storage',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
      }),
    }
  )
)
