/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Ensure path aliases work correctly
  experimental: {
    // This is not needed in Next.js 14, but keeping for compatibility
  }
};

export default nextConfig;

