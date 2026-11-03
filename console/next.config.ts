import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits .next/standalone/server.js so the runtime image carries no node_modules.
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
