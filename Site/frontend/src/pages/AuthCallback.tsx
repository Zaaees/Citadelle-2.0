import { useEffect, useState, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { authService } from '../services/auth'
import { Loader2, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'

export default function AuthCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { setAuth } = useAuthStore()
  const [error, setError] = useState<string | null>(null)
  const hasAttempted = useRef(false)

  useEffect(() => {
    // Empêcher les appels multiples (React Strict Mode en dev)
    if (hasAttempted.current) return
    hasAttempted.current = true

    const code = searchParams.get('code')
    const errorParam = searchParams.get('error')

    if (errorParam) {
      setError('Authentification annulée ou refusée')
      toast.error('Authentification annulée')
      setTimeout(() => navigate('/'), 3000)
      return
    }

    if (!code) {
      setError('Code d\'authentification manquant')
      toast.error('Erreur d\'authentification')
      setTimeout(() => navigate('/'), 3000)
      return
    }

    // Échanger le code contre un token
    const authenticate = async () => {
      try {
        const authResponse = await authService.login(code)

        // Sauvegarder l'auth dans le store
        setAuth(authResponse.user, authResponse.access_token)

        // Afficher un message de succès
        toast.success(`Bienvenue, ${authResponse.user.global_name || authResponse.user.username} !`)

        // Rediriger vers la page d'accueil
        setTimeout(() => navigate('/'), 1000)
      } catch (err) {
        console.error('Erreur d\'authentification:', err)
        setError('Erreur lors de l\'authentification avec Discord')
        toast.error('Erreur d\'authentification')
        setTimeout(() => navigate('/'), 3000)
      }
    }

    authenticate()
  }, [searchParams, navigate, setAuth])

  if (error) {
    return (
      <div className="container mx-auto px-4 py-20">
        <div className="max-w-md mx-auto">
          <div className="card text-center">
            <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertCircle className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-2xl font-display font-bold text-white mb-4">
              Erreur d'authentification
            </h2>
            <p className="text-gray-300 mb-6">{error}</p>
            <p className="text-sm text-gray-400">Redirection vers la page d'accueil...</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-20">
      <div className="max-w-md mx-auto">
        <div className="card text-center">
          <div className="w-16 h-16 bg-primary/20 rounded-full flex items-center justify-center mx-auto mb-4 animate-pulse">
            <Loader2 className="w-8 h-8 text-primary animate-spin" />
          </div>
          <h2 className="text-2xl font-display font-bold text-white mb-4">
            Authentification en cours...
          </h2>
          <p className="text-gray-300 mb-6">Connexion avec votre compte Discord</p>
          <div className="flex items-center justify-center gap-2 text-sm text-gray-400">
            <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
            <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
            <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
          </div>
        </div>
      </div>
    </div>
  )
}
