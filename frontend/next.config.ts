import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:18741";
const isStaticExport = process.env.NEXT_OUTPUT === "export";

const nextConfig: NextConfig = isStaticExport
  ? {
      output: "export",
      trailingSlash: true,
      images: { unoptimized: true },
    }
  : {
      async rewrites() {
        return [
          { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
          { source: "/health", destination: `${API_ORIGIN}/health` },
        ];
      },
    };

export default nextConfig;
