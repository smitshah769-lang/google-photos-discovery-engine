import type { NextConfig } from "next";

const api = process.env.DISCOVERY_API_URL || "http://127.0.0.1:8765";

const nextConfig: NextConfig = {
  async rewrites() {
    return {
      beforeFiles: [],
      afterFiles: [
        { source: "/insights", destination: `${api}/insights` },
        { source: "/categories", destination: `${api}/categories` },
        { source: "/methodology", destination: `${api}/methodology` },
        { source: "/quality", destination: `${api}/quality` },
        { source: "/chrome", destination: `${api}/chrome` },
        { source: "/evidence", destination: `${api}/evidence` },
        { source: "/items/:id", destination: `${api}/items/:id` },
        { source: "/search", destination: `${api}/search` },
        { source: "/handoff", destination: `${api}/handoff` },
      ],
      fallback: [],
    };
  },
};

export default nextConfig;
