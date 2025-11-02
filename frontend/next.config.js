// frontend/next.config.js
/** @type {import('next').NextConfig} */

const nextConfig = {
  output: "standalone", // creates a minimal server runtime in .next/standalone (optional but recommended)
  reactStrictMode: true,

  async rewrites() {
    // If we don't have a BACKEND_URL in prod, return no rewrites to avoid bad routes.
    const backend = process.env.BACKEND_URL?.replace(/\/+$/, "");
    if (!backend) {
      console.warn("[next.config.js] BACKEND_URL not set, skipping rewrite");
      return [];
    }
    return [
      { source: "/api/chat", destination: `${process.env.BACKEND_URL}/chat` },
      {
        // Frontend calls: fetch('/chat', ...)
        source: 
        // "/chat",
        // Next.js server proxies to your backend:
        // destination: `${backend}/chat`,
        '/auth/:path*', 
        destination: `${process.env.BACKEND_URL}/auth/:path*`
      },
    ];
  },
};

module.exports = nextConfig;
