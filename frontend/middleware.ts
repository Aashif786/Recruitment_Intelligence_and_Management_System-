import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * RIMS Global Middleware
 * Handles server-side redirection for unauthorized access to dashboard routes.
 */
export function middleware(request: NextRequest) {
  const token = request.cookies.get('access_token')?.value
  const { pathname } = request.nextUrl

  // 1. Protect all /dashboard routes
  if (pathname.startsWith('/dashboard')) {
    if (!token) {
      const url = request.nextUrl.clone()
      url.pathname = '/auth/login'
      url.searchParams.set('expired', 'true')
      url.searchParams.set('callbackUrl', pathname)
      
      console.log(`[Middleware] Unauthorized access to ${pathname}, redirecting to login.`)
      return NextResponse.redirect(url)
    }
  }

  // 2. Prevent logged-in users from hitting /auth/login (optional but good UX)
  if (pathname === '/auth/login' && token) {
    const url = request.nextUrl.clone()
    url.pathname = '/dashboard'
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

// Ensure the middleware only runs on relevant routes to maintain performance
export const config = {
  matcher: [
    '/dashboard/:path*',
    '/auth/login'
  ],
}
