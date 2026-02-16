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
      {
        source: "/api/chat/:path*",
        destination: `${backend}/chat/:path*`
      },
      {
        source: "/auth/:path*", 
        destination: `${backend}/auth/:path*`
      },
      { 
        source: "/api/questions/:path*",
        destination: `${backend}/questions/:path*` 
      },
      {
        source: "/api/quiz/:path*",
        destination: `${backend}/quiz/:path*`,
      },
      {
        source: "/api/demographics/:path*",
        destination: `${backend}/demographics/:path*`,
      },
      {
        source: "/api/surveys/:path*",
        destination: `${backend}/surveys/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
