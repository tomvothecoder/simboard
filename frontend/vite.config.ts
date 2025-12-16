import react from '@vitejs/plugin-react';
import fs from "fs";
import path from "path";
import { defineConfig, loadEnv } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

// Determine the active application environment.
// Defaults to "local" if not provided.
const appEnv = process.env.APP_ENV ?? "local";

// Load env vars from .envs/<APP_ENV>/frontend.env
const envDir = path.resolve(__dirname, `.envs/${appEnv}`);
const env = loadEnv(appEnv, envDir, "");

// ---------------------------------------------
// Filter ONLY safe frontend variables (VITE_*)
// ---------------------------------------------
const viteEnv: Record<string, string> = {};
for (const key in env) {
  if (key.startsWith("VITE_")) {
    viteEnv[key] = env[key];
  }
}

// ---------------------------------------------
// Certificate path setup
// ---------------------------------------------
const keyPath = viteEnv.VITE_SSL_KEY ?? "../certs/dev.key";
const certPath = viteEnv.VITE_SSL_CERT ?? "../certs/dev.crt";

// Resolve relative paths based on the location of this config file,
// not the working directory (important for Docker/PNPM/WSL setups)
const resolveIfExists = (p: string) => {
  const full = path.resolve(__dirname, p);
  return fs.existsSync(full) ? full : null;
};

const finalKey = resolveIfExists(keyPath);
const finalCert = resolveIfExists(certPath);

// ---------------------------------------------
// Optional safety checks
// ---------------------------------------------

// Warn in local development if HTTPS will not be enabled
if (!finalKey || !finalCert) {
  console.warn("⚠️  HTTPS disabled: missing dev.key or dev.crt");
}

// In CI/staging/prod you may require HTTPS and fail fast
if (process.env.CI && (!finalKey || !finalCert)) {
  throw new Error("❌ SSL certificates missing in CI environment.");
}

// ---------------------------------------------
// Final Vite config
// ---------------------------------------------
export default defineConfig({
  plugins: [react(), tsconfigPaths()],

  // Expose ONLY VITE_* variables to the client
  define: {
    "import.meta.env": viteEnv,
  },

  server: {
    host: "127.0.0.1",
    port: 5173,

    // Enable HTTPS only if certs are available.
    // Otherwise Vite defaults to HTTP.
    https:
      finalKey && finalCert
        ? {
            key: fs.readFileSync(finalKey),
            cert: fs.readFileSync(finalCert),
          }
        : undefined,
  },
});
