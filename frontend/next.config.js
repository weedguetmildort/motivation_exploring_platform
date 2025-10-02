// frontend/next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone", // creates a minimal server runtime in .next/standalone (optional but recommended)
  reactStrictMode: true,
};
module.exports = nextConfig;
