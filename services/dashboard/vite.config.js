import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Jane's Jeans store-ops dashboard. Standalone dev server, no backend
// required — reads fixture data by default (see src/fixtures).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
