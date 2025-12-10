import { useAuthStore } from '../stores/authStore'
import { authService } from '../services/auth'
import { Sparkles, Zap, Users, ArrowRight } from 'lucide-react'

export default function Home() {
  const { user, isAuthenticated } = useAuthStore()

  const handleDiscordLogin = () => {
    window.location.href = authService.getDiscordAuthUrl()
  }

  if (isAuthenticated() && user) {
    return (
      <div className="container mx-auto px-4 py-20">
        <div className="max-w-4xl mx-auto">
          {/* Bienvenue */}
          <div className="text-center mb-12">
            <h1 className="text-5xl font-display font-bold text-white mb-4">
              Bienvenue, {user.global_name || user.username} ! ✨
            </h1>
            <p className="text-xl text-gray-300">
              Vous êtes connecté et prêt à collectionner des cartes !
            </p>
          </div>

          {/* Cartes de fonctionnalités */}
          <div className="grid md:grid-cols-3 gap-6">
            <div className="card hover:border-primary transition-colors cursor-pointer">
              <div className="w-12 h-12 bg-primary/20 rounded-lg flex items-center justify-center mb-4">
                <Sparkles className="w-6 h-6 text-primary" />
              </div>
              <h3 className="text-lg font-display font-bold text-white mb-2">Galerie</h3>
              <p className="text-gray-400 text-sm">
                Explorez toutes les cartes disponibles et consultez votre collection
              </p>
              <button className="mt-4 text-primary text-sm font-medium flex items-center gap-2">
                Voir la galerie <ArrowRight className="w-4 h-4" />
              </button>
            </div>

            <div className="card hover:border-secondary transition-colors cursor-pointer">
              <div className="w-12 h-12 bg-secondary/20 rounded-lg flex items-center justify-center mb-4">
                <Zap className="w-6 h-6 text-secondary" />
              </div>
              <h3 className="text-lg font-display font-bold text-white mb-2">Tirages</h3>
              <p className="text-gray-400 text-sm">
                Effectuez vos tirages journaliers et sacrificiels pour obtenir de nouvelles cartes
              </p>
              <button className="mt-4 text-secondary text-sm font-medium flex items-center gap-2">
                Tirer des cartes <ArrowRight className="w-4 h-4" />
              </button>
            </div>

            <div className="card hover:border-accent transition-colors cursor-pointer">
              <div className="w-12 h-12 bg-accent/20 rounded-lg flex items-center justify-center mb-4">
                <Users className="w-6 h-6 text-accent" />
              </div>
              <h3 className="text-lg font-display font-bold text-white mb-2">Échanges</h3>
              <p className="text-gray-400 text-sm">
                Échangez vos cartes avec d'autres collectionneurs sur le tableau d'échanges
              </p>
              <button className="mt-4 text-accent text-sm font-medium flex items-center gap-2">
                Voir les échanges <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Info */}
          <div className="mt-12 card bg-gradient-to-br from-primary/10 to-secondary/10 border-primary/30">
            <h3 className="text-lg font-display font-bold text-white mb-2">
              🚧 Site en construction
            </h3>
            <p className="text-gray-300 text-sm">
              L'authentification Discord fonctionne ! 🎉 Les pages Galerie, Tirages et Échanges
              seront bientôt disponibles. En attendant, vous pouvez utiliser le bot Discord pour
              accéder à toutes les fonctionnalités.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-20">
      <div className="max-w-4xl mx-auto">
        {/* Hero Section */}
        <div className="text-center mb-16">
          <div className="inline-block mb-6">
            <div className="w-20 h-20 bg-gradient-to-br from-primary to-secondary rounded-2xl flex items-center justify-center shadow-2xl animate-float">
              <Sparkles className="w-10 h-10 text-white" />
            </div>
          </div>

          <h1 className="text-6xl font-display font-bold text-white mb-6 bg-gradient-to-r from-primary via-secondary to-accent bg-clip-text text-transparent">
            Citadelle Cards
          </h1>

          <p className="text-xl text-gray-300 mb-8 max-w-2xl mx-auto">
            Plongez dans un univers fantastique de collection de cartes. Tirez, échangez et
            complétez votre collection de cartes uniques inspirées de votre serveur Discord
            préféré !
          </p>

          <button
            onClick={handleDiscordLogin}
            className="btn btn-discord text-lg px-8 py-4 inline-flex items-center gap-3"
          >
            <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
              <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515a.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0a12.64 12.64 0 0 0-.617-1.25a.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057a19.9 19.9 0 0 0 5.993 3.03a.078.078 0 0 0 .084-.028a14.09 14.09 0 0 0 1.226-1.994a.076.076 0 0 0-.041-.106a13.107 13.107 0 0 1-1.872-.892a.077.077 0 0 1-.008-.128a10.2 10.2 0 0 0 .372-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127a12.299 12.299 0 0 1-1.873.892a.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028a19.839 19.839 0 0 0 6.002-3.03a.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.956-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.955-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.946 2.418-2.157 2.418z" />
            </svg>
            Se connecter avec Discord
          </button>

          <p className="text-sm text-gray-400 mt-4">
            Connectez-vous avec votre compte Discord pour accéder à vos cartes
          </p>
        </div>

        {/* Features */}
        <div className="grid md:grid-cols-3 gap-8 mt-20">
          <div className="text-center">
            <div className="w-16 h-16 bg-primary/20 rounded-xl flex items-center justify-center mx-auto mb-4">
              <Sparkles className="w-8 h-8 text-primary" />
            </div>
            <h3 className="text-xl font-display font-bold text-white mb-2">Collection Unique</h3>
            <p className="text-gray-400">
              Découvrez des cartes rares et collectionnez-les toutes pour compléter votre galerie
            </p>
          </div>

          <div className="text-center">
            <div className="w-16 h-16 bg-secondary/20 rounded-xl flex items-center justify-center mx-auto mb-4">
              <Zap className="w-8 h-8 text-secondary" />
            </div>
            <h3 className="text-xl font-display font-bold text-white mb-2">Tirages Quotidiens</h3>
            <p className="text-gray-400">
              Obtenez de nouvelles cartes chaque jour avec les tirages journaliers et sacrificiels
            </p>
          </div>

          <div className="text-center">
            <div className="w-16 h-16 bg-accent/20 rounded-xl flex items-center justify-center mx-auto mb-4">
              <Users className="w-8 h-8 text-accent" />
            </div>
            <h3 className="text-xl font-display font-bold text-white mb-2">Système d'Échanges</h3>
            <p className="text-gray-400">
              Échangez vos doublons avec d'autres joueurs pour compléter votre collection
            </p>
          </div>
        </div>

        {/* Rarity info */}
        <div className="mt-20 card">
          <h2 className="text-2xl font-display font-bold text-white mb-6 text-center">
            Catégories de Rareté
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="p-3 bg-dark-700 rounded-lg border border-purple-500/30">
              <div className="w-3 h-3 bg-purple-500 rounded-full mb-2"></div>
              <p className="text-sm font-medium text-white">Secrète</p>
              <p className="text-xs text-gray-400">0.5% de chance</p>
            </div>
            <div className="p-3 bg-dark-700 rounded-lg border border-yellow-500/30">
              <div className="w-3 h-3 bg-yellow-500 rounded-full mb-2"></div>
              <p className="text-sm font-medium text-white">Fondateur</p>
              <p className="text-xs text-gray-400">1% de chance</p>
            </div>
            <div className="p-3 bg-dark-700 rounded-lg border border-pink-500/30">
              <div className="w-3 h-3 bg-pink-500 rounded-full mb-2"></div>
              <p className="text-sm font-medium text-white">Historique</p>
              <p className="text-xs text-gray-400">2% de chance</p>
            </div>
            <div className="p-3 bg-dark-700 rounded-lg border border-red-500/30">
              <div className="w-3 h-3 bg-red-500 rounded-full mb-2"></div>
              <p className="text-sm font-medium text-white">Maître</p>
              <p className="text-xs text-gray-400">6% de chance</p>
            </div>
            <div className="p-3 bg-dark-700 rounded-lg border border-blue-500/30">
              <div className="w-3 h-3 bg-blue-500 rounded-full mb-2"></div>
              <p className="text-sm font-medium text-white">Élèves</p>
              <p className="text-xs text-gray-400">42% de chance</p>
            </div>
            <div className="p-3 bg-dark-700 rounded-lg border border-green-500/30">
              <div className="w-3 h-3 bg-green-500 rounded-full mb-2"></div>
              <p className="text-sm font-medium text-white">Autre</p>
              <p className="text-xs text-gray-400">25.7% de chance</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
