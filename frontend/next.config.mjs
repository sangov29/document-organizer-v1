const backend = process.env.BACKEND_INTERNAL_URL ?? 'http://localhost:8000';

/** @type {import('next').NextConfig} */
const nextConfig = {
  // The acceptance browser reaches the development server through Docker's
  // internal service hostname. Next.js 16 otherwise rejects its dev-only
  // asset/HMR origin, which prevents client hydration in that environment.
  allowedDevOrigins: ['frontend'],
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backend}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
