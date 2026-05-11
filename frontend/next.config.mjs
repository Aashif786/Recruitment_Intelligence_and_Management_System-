/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  allowedDevOrigins: ['127.0.0.1', 'localhost:3000'],
  basePath: '/calrims',
  trailingSlash: true,
  devIndicators: {
    appIsrStatus: false,
    buildActivity: false,
    buildActivityPosition: 'bottom-right',
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async redirects() {
    return [
      {
        source: '/',
        destination: '/calrims/',
        permanent: false,
        basePath: false,
      },
      {
        source: '/auth/:path*',
        destination: '/calrims/auth/:path*',
        permanent: false,
        basePath: false,
      },
      {
        source: '/dashboard/:path*',
        destination: '/calrims/dashboard/:path*',
        permanent: false,
        basePath: false,
      },
      {
        source: '/jobs/:path*',
        destination: '/calrims/jobs/:path*',
        permanent: false,
        basePath: false,
      },
      {
        source: '/interview/:path*',
        destination: '/calrims/interview/:path*',
        permanent: false,
        basePath: false,
      },
    ]
  },
  async rewrites() {
    return [
      {
        source: '/api/((?!generate-pdf|health).*)',
        destination: 'http://127.0.0.1:10000/api/:1',
      },
    ]
  }
}
export default nextConfig
