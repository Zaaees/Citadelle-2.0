import { Sparkles } from 'lucide-react'
import { useState, useEffect } from 'react'
import type { Card } from '../../types/card'
import { CATEGORY_COLORS } from '../../types/card'

interface CardItemProps {
  card: Card
  count?: number // Nombre d'exemplaires possédés (optionnel)
  onClick?: () => void
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const IMAGE_TIMEOUT = 8000 // 8 secondes

export default function CardItem({ card, count, onClick }: CardItemProps) {
  const colors = CATEGORY_COLORS[card.category]
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [showPlaceholder, setShowPlaceholder] = useState(false)

  // Timeout pour afficher le placeholder si l'image ne charge pas
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!imageLoaded && !imageError) {
        console.warn(`Image timeout for ${card.name} (${card.file_id})`)
        setShowPlaceholder(true)
        setImageError(true)
      }
    }, IMAGE_TIMEOUT)

    return () => clearTimeout(timer)
  }, [imageLoaded, imageError, card.name, card.file_id])

  return (
    <div
      className={`
        card group relative overflow-hidden cursor-pointer
        hover:scale-105 hover:shadow-2xl hover:shadow-primary/20
        transition-all duration-300
        ${onClick ? 'hover:border-primary' : ''}
      `}
      onClick={onClick}
    >
      {/* Badge catégorie */}
      <div className={`absolute top-2 left-2 z-10 px-2 py-1 rounded-md bg-gradient-to-r ${colors.bg} ${colors.border} border backdrop-blur-sm`}>
        <span className={`text-xs font-bold ${colors.text}`}>{card.category}</span>
      </div>

      {/* Badge Full */}
      {card.is_full && (
        <div className="absolute top-2 right-2 z-10 px-2 py-1 rounded-md bg-gradient-to-r from-yellow-600 to-amber-600 border border-yellow-400">
          <div className="flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-yellow-100" />
            <span className="text-xs font-bold text-yellow-100">FULL</span>
          </div>
        </div>
      )}

      {/* Nombre d'exemplaires */}
      {count !== undefined && count > 0 && (
        <div className="absolute bottom-2 right-2 z-10 w-8 h-8 rounded-full bg-primary/90 border-2 border-white flex items-center justify-center">
          <span className="text-sm font-bold text-white">×{count}</span>
        </div>
      )}

      {/* Image de la carte */}
      <div className="aspect-[2/3] bg-gradient-to-br from-dark-800 to-dark-900 rounded-lg overflow-hidden mb-3 relative">
        {card.file_id ? (
          <>
            {/* Skeleton loader */}
            {!imageLoaded && !imageError && (
              <div className="absolute inset-0 bg-dark-800 animate-pulse flex items-center justify-center">
                <Sparkles className="w-12 h-12 text-dark-600 opacity-50 animate-spin" />
              </div>
            )}

            {/* Image */}
            <img
              src={`${API_URL}/api/cards/image/${card.file_id}`}
              alt={card.name}
              className={`w-full h-full object-cover group-hover:scale-110 transition-all duration-300 ${
                imageLoaded ? 'opacity-100' : 'opacity-0'
              }`}
              loading="lazy"
              onLoad={() => setImageLoaded(true)}
              onError={(e) => {
                // Fallback si l'image ne charge pas
                console.error(`Failed to load image for ${card.name} (${card.file_id})`)
                setImageError(true)
                setImageLoaded(true)
              }}
            />

            {/* Error state */}
            {imageError && (
              <div className="absolute inset-0 bg-gradient-to-br from-dark-800 to-dark-900 flex items-center justify-center p-4">
                <div className="text-center">
                  <div className={`w-16 h-16 mx-auto mb-3 rounded-full bg-gradient-to-r ${colors.bg} opacity-20 flex items-center justify-center`}>
                    <Sparkles className="w-8 h-8 text-white opacity-50" />
                  </div>
                  <p className="text-xs text-gray-400 font-medium">{card.name}</p>
                  <p className="text-xs text-gray-600 mt-1">{card.category}</p>
                </div>
              </div>
            )}
          </>
        ) : (
          // Placeholder si pas d'image
          <div className="w-full h-full flex items-center justify-center">
            <div className="text-center text-gray-500">
              <Sparkles className="w-12 h-12 mx-auto mb-2 opacity-30" />
              <p className="text-sm">Aucune image</p>
            </div>
          </div>
        )}
      </div>

      {/* Nom de la carte */}
      <h3 className="text-sm font-semibold text-white text-center line-clamp-2 px-2">
        {card.name}
      </h3>

      {/* Indicateur de rareté (barre en bas) */}
      <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r ${colors.bg} opacity-60"></div>
    </div>
  )
}
