import react from '@vitejs/plugin-react';
import fs from "fs";
import path from "path";
import { defineConfig } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    https: {
      key: fs.readFileSync(path.resolve(__dirname, "../certs/key.pem")),
      cert: fs.readFileSync(path.resolve(__dirname, "../certs/cert.pem")),
    },
  },
});
