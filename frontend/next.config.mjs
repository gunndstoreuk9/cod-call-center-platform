/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  poweredByHeader: false,

  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: 'https://codops.up.railway.app/api/v1/:path*',
      },
    ]
  },
}

export default nextConfig
