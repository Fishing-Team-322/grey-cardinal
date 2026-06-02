/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BRAIN_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
