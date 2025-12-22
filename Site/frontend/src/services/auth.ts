import api from './api'

export interface User {
  // user_id est une string pour éviter la perte de précision en JavaScript
  // (les IDs Discord dépassent 2^53, limite des nombres JS safe)
  user_id: string
  username: string
  discriminator: string
  global_name?: string
  avatar?: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
  expires_in: number
}

export const authService = {
  /**
   * Obtient l'URL d'autorisation Discord
   */
  getDiscordAuthUrl(): string {
    const clientId = import.meta.env.VITE_DISCORD_CLIENT_ID
    const redirectUri = import.meta.env.VITE_DISCORD_REDIRECT_URI
    const scope = 'identify'

    return `https://discord.com/api/oauth2/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(
      redirectUri
    )}&response_type=code&scope=${scope}`
  },

  /**
   * Échange le code OAuth2 contre un token JWT
   */
  async login(code: string): Promise<AuthResponse> {
    const response = await api.get<AuthResponse>('/api/auth/discord/callback', {
      params: { code },
    })

    return response.data
  },

  /**
   * Récupère les informations de l'utilisateur actuellement connecté
   */
  async getMe(): Promise<User> {
    const response = await api.get<User>('/api/auth/me')
    return response.data
  },

  /**
   * Déconnecte l'utilisateur
   */
  async logout(): Promise<void> {
    try {
      await api.post('/api/auth/logout')
    } catch (error) {
      console.error('Erreur lors de la déconnexion:', error)
    }
  },

  /**
   * Vérifie si l'utilisateur est authentifié
   */
  async checkAuthStatus(): Promise<{ authenticated: boolean; user_id?: string; username?: string }> {
    try {
      const response = await api.get('/api/auth/status')
      return response.data
    } catch (error) {
      return { authenticated: false }
    }
  },

  /**
   * Construit l'URL de l'avatar Discord
   */
  getAvatarUrl(user: User): string {
    if (user.avatar) {
      // Les avatars animés commencent par 'a_' - utiliser gif dans ce cas
      const extension = user.avatar.startsWith('a_') ? 'gif' : 'png'
      return `https://cdn.discordapp.com/avatars/${user.user_id}/${user.avatar}.${extension}?size=128`
    }

    // Avatar par défaut Discord basé sur le discriminator
    // Si pas de discriminator (nouveau système), utiliser l'ID
    // user_id est maintenant une string, on utilise BigInt pour les calculs précis
    const defaultAvatarIndex = user.discriminator && user.discriminator !== '0'
      ? parseInt(user.discriminator) % 5
      : Number((BigInt(user.user_id) >> BigInt(22)) % BigInt(6))

    return `https://cdn.discordapp.com/embed/avatars/${defaultAvatarIndex}.png`
  },
}
