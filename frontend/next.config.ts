import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:18741";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
      { source: "/health", destination: `${API_ORIGIN}/health` },
    ];
  },
};

export default nextConfig;
