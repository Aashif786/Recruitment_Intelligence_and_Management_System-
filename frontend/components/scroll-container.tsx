'use client'

import React from 'react'
import { usePathname } from 'next/navigation'
import { ErrorBoundary } from '@/components/error-boundary'

interface ScrollContainerProps {
  children: React.ReactNode
}

/**
 * ScrollContainer handles the dual-scrollbar issue by conditionally 
 * disabling root scrolling when the user is in the dashboard.
 * Dashboard layouts handle their own scrolling to keep the sidebar fixed.
 */
export function ScrollContainer({ children }: ScrollContainerProps) {
  const pathname = usePathname()
  const isDashboard = pathname?.startsWith('/dashboard')
  const isAuth = pathname?.startsWith('/auth')

  return (
    <main className={`flex-1 min-h-0 w-full flex flex-col ${isDashboard || isAuth ? 'overflow-hidden' : 'overflow-y-auto'}`}>
      <ErrorBoundary>
        <div className="h-full flex flex-col">
          {children}
        </div>
      </ErrorBoundary>
    </main>
  )
}
