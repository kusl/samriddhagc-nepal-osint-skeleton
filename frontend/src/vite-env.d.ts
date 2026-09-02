/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  // Public deployment switches — see src/config/deployment.ts
  readonly VITE_PUBLIC_ONLY?: string
  readonly VITE_DISABLED_PRESETS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// Type declarations for cytoscape layout plugins
declare module 'cytoscape-fcose' {
  const fcose: cytoscape.Ext
  export default fcose
}

declare module 'cytoscape-cola' {
  const cola: cytoscape.Ext
  export default cola
}
