/// <reference types="vite/client" />

interface ImportMetaEnv {
    readonly VITE_API_URL: string
    readonly VITE_DISCORD_CLIENT_ID: string
    readonly VITE_DISCORD_REDIRECT_URI: string
    readonly VITE_WS_URL: string
    readonly VITE_ENVIRONMENT: string
}

interface ImportMeta {
    readonly env: ImportMetaEnv
}
