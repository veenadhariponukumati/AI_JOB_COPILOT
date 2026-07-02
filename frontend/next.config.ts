import type { NextConfig } from "next";

// Locally, stray lockfiles above this repo (in the home directory) make
// Next.js walk up and infer the wrong monorepo root, so we pin it to this
// folder. On Vercel, the build sandbox has no such stray lockfiles and
// Vercel sets its own outputFileTracingRoot to the build root regardless -
// applying our override there just creates a same-value-required warning
// with no benefit, so only apply it outside Vercel's environment.
const isVercel = !!process.env.VERCEL;

const nextConfig: NextConfig = {
  ...(isVercel
    ? {}
    : {
        outputFileTracingRoot: __dirname,
        turbopack: { root: __dirname },
      }),
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/backend/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
