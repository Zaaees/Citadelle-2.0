import { Outlet, Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { authService } from '../../services/auth'
import { LogOut, Sparkles, Library, Dices, Repeat2, User } from 'lucide-react'
import toast from 'react-hot-toast'

export default function Layout() {
  const { user, isAuthenticated, clearAuth } = useAuthStore()
  const location = useLocation()

  const handleLogout = async () => {
    try {
      await authService.logout()
      clearAuth()
      toast.success('Déconnexion réussie')
    } catch (error) {
      console.error('Erreur de déconnexion:', error)
      clearAuth() // Déconnecter quand même côté client
    }
  }

  const handleImageError = (e: React.SyntheticEvent<HTMLImageElement>) => {
    // Fallback vers un avatar par défaut si l'image ne charge pas
    // Utilise un gradient entre primary et secondary pour un meilleur effet visuel
    e.currentTarget.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(user?.username || 'User')}&background=random&bold=true&size=128`
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-dark-900 via-dark-800 to-dark-900">
      {/* Header */}
      <header className="border-b border-dark-700 bg-dark-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
              <div className="w-10 h-10 bg-gradient-to-br from-primary to-secondary rounded-lg flex items-center justify-center">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-display font-bold text-white">Citadelle Cards</h1>
                <p className="text-xs text-gray-400">Système de cartes fantastique</p>
              </div>
            </Link>

            {/* Navigation (si connecté) */}
            {isAuthenticated() && user ? (
              <nav className="hidden lg:flex items-center gap-2">
                <Link
                  to="/gallery"
                  className={`
                    flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all
                    ${
                      location.pathname === '/gallery'
                        ? 'bg-gradient-to-r from-primary to-secondary text-white'
                        : 'text-gray-300 hover:bg-dark-700 hover:text-white'
                    }
                  `}
                >
                  <Library className="w-4 h-4" />
                  <span>Galerie</span>
                </Link>
                <Link
                  to="/draw"
                  className={`
                    flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all
                    ${
                      location.pathname === '/draw'
                        ? 'bg-gradient-to-r from-primary to-secondary text-white'
                        : 'text-gray-300 hover:bg-dark-700 hover:text-white'
                    }
                  `}
                >
                  <Dices className="w-4 h-4" />
                  <span>Tirages</span>
                </Link>
                <Link
                  to="/trade"
                  className={`
                    flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all
                    ${
                      location.pathname === '/trade'
                        ? 'bg-gradient-to-r from-primary to-secondary text-white'
                        : 'text-gray-300 hover:bg-dark-700 hover:text-white'
                    }
                  `}
                >
                  <Repeat2 className="w-4 h-4" />
                  <span>Échanges</span>
                </Link>
                <Link
                  to="/profile"
                  className={`
                    flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all
                    ${
                      location.pathname === '/profile'
                        ? 'bg-gradient-to-r from-primary to-secondary text-white'
                        : 'text-gray-300 hover:bg-dark-700 hover:text-white'
                    }
                  `}
                >
                  <User className="w-4 h-4" />
                  <span>Profil</span>
                </Link>
              </nav>
            ) : null}

            {/* User menu */}
            {isAuthenticated() && user ? (
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-3">
                  <img
                    src={authService.getAvatarUrl(user)}
                    alt={user.username}
                    className="w-10 h-10 rounded-full border-2 border-primary"
                    onError={handleImageError}
                  />
                  <div className="hidden md:block">
                    <p className="text-sm font-medium text-white">
                      {user.global_name || user.username}
                    </p>
                    <p className="text-xs text-gray-400">@{user.username}</p>
                  </div>
                </div>

                <button
                  onClick={handleLogout}
                  className="btn bg-dark-700 hover:bg-dark-600 text-gray-300 hover:text-white flex items-center gap-2"
                >
                  <LogOut className="w-4 h-4" />
                  <span className="hidden sm:inline">Déconnexion</span>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      {/* Main content */}
      <main>
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t border-dark-700 bg-dark-900/50 backdrop-blur-sm mt-20">
        <div className="container mx-auto px-4 py-8">
          <div className="text-center text-gray-400 text-sm">
            <p>🎴 Citadelle Cards - Système de cartes pour le serveur Discord Citadelle</p>
            <p className="mt-2">Développé avec ❤️ par Claude Code</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
