import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * RIMS Global Proxy
 * Handles server-side redirection for unauthorized access to dashboard routes.
 */
export function proxy(request: NextRequest) {
  const token = request.cookies.get('access_token')?.value
  const { pathname } = request.nextUrl

  // 1. Protect all /dashboard, /company, and /offer routes
  const protectedRoutes = ['/dashboard', '/company', '/offer', '/jobs/create', '/support']
  const isProtectedRoute = protectedRoutes.some(route => pathname.startsWith(route))

  if (isProtectedRoute) {
    if (!token) {
      const url = request.nextUrl.clone()
      url.pathname = '/auth/login'
      url.searchParams.set('from', pathname)
      return NextResponse.redirect(url)
    }
  }

  return NextResponse.next()
}

// Ensure the proxy only runs on relevant routes to maintain performance
export const config = {
  matcher: [
    '/dashboard/:path*',
    '/company/:path*',
    '/offer/:path*',
    '/jobs/create/:path*',
    '/support/:path*',
    '/auth/login'
  ],
}
