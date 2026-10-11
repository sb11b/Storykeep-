import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:18741";
const isStaticExport = process.env.NEXT_OUTPUT === "export";

// A static export has no dev/prod server to proxy /api through, so the client
// must call the API by absolute URL. Default to the Railway deployment and let
// a build override it with NEXT_PUBLIC_API_ORIGIN. Dev builds (rewrites below)
// leave this empty and keep using relative paths.
const DEFAULT_API_ORIGIN = "https://storykeep-production.up.railway.app";

const nextConfig: NextConfig = isStaticExport
  ? {
      output: "export",
      trailingSlash: true,
      images: { unoptimized: true },
      env: {
        NEXT_PUBLIC_API_ORIGIN: process.env.NEXT_PUBLIC_API_ORIGIN ?? DEFAULT_API_ORIGIN,
      },
    }
  : {
      async rewrites() {
        return [
          { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
          { source: "/health", destination: `${API_ORIGIN}/health` },
          { source: "/about", destination: `${API_ORIGIN}/about` },
        ];
      },
    };

export default nextConfig;
