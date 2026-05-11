'use client'

import React from "react"

import { useAuth } from '@/app/dashboard/lib/auth-context'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { SidebarProvider } from '@/components/animate-ui/components/radix/sidebar'
import { AppSidebar } from '@/components/app-sidebar'
import { UserNav } from '@/components/user-nav'
import { ToggleTheme } from '@/components/lightswind/toggle-theme'
import { NotificationBell } from '@/components/notification-bell'
import { Search } from 'lucide-react'
import { SWRConfig, mutate as globalMutate } from 'swr'
import { fetcher } from '@/app/dashboard/lib/swr-fetcher'
import { useSessionIntelligence } from '@/hooks/use-session-intelligence'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { isAuthenticated, isLoading, isOffline } = useAuth()
  const router = useRouter()
  const [isMounted, setIsMounted] = useState(false)

  // Session intelligence: auto-tracks page visits
  useSessionIntelligence()

  useEffect(() => {
    setIsMounted(true)
  }, [])

  useEffect(() => {
    // Only redirect to login if we are CERTAIN that the user is not authenticated
    // and the loading process has finished without network errors.
    if (isMounted && !isLoading && !isOffline && !isAuthenticated) {
      router.push('/auth/login?expired=true')
    }
  }, [isAuthenticated, isLoading, isOffline, isMounted, router])

  useEffect(() => {
    const handleDataMutation = (event: Event) => {
      const customEvent = event as CustomEvent<{ keys?: string[] }>
      const keys = customEvent.detail?.keys || []
      for (const key of keys) {
        globalMutate(
          (cacheKey) => typeof cacheKey === 'string' && (cacheKey === key || cacheKey.startsWith(`${key}?`)),
          undefined,
          { revalidate: true },
        )
      }
    }

    window.addEventListener('rims:data-mutated', handleDataMutation)
    return () => window.removeEventListener('rims:data-mutated', handleDataMutation)
  }, [])

  if (!isMounted || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

  if (isOffline && !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-6 text-center">
        <div className="max-w-md space-y-6">
          <div className="w-20 h-20 bg-destructive/10 rounded-full flex items-center justify-center mx-auto border border-destructive/20">
            <span className="text-4xl text-destructive font-black">!</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">Connection Lost</h1>
          <p className="text-muted-foreground leading-relaxed">
            Unable to connect to the recruitment server. Please check your internet connection or verify the backend is running.
          </p>
          <button 
            onClick={() => window.location.reload()}
            className="px-6 py-2 bg-primary text-primary-foreground rounded-lg font-bold hover:opacity-90 transition-all"
          >
            Retry Connection
          </button>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    // Fallback while redirecting
    return null
  }

  return (
    <SWRConfig
      value={{
        fetcher,
        revalidateOnFocus: false,   // disabled: prevents refetch on every tab focus
        revalidateOnReconnect: true,
        dedupingInterval: 15_000,   // increased: reduces duplicate requests on navigation
        errorRetryCount: 3,
        shouldRetryOnError: true
      }}
    >
      <SidebarProvider>
        {/* SidebarProvider div uses flex-1 min-h-0 so it properly fills the flex-col parent (ScrollContainer <main>) */}
        <div className="flex flex-1 min-h-0 w-full bg-transparent relative overflow-hidden">
          {/* subtle inner background for dashboard content */}
          <div className="pointer-events-none absolute inset-0 z-0 opacity-80">
            <div className="absolute inset-0 bg-background/95" />
          </div>

          <AppSidebar />

          {/* Right panel: flex-1 min-h-0 so it shrinks properly; overflow-hidden clips children */}
          <div className="flex-1 min-h-0 flex flex-col relative z-10 transition-all duration-300 overflow-hidden">
            {/* Single scroll zone - this is the ONLY element that scrolls */}
            <div className="flex-1 min-h-0 p-4 md:p-6 lg:p-8 overflow-y-auto overflow-x-hidden">
              <div className="max-w-[1600px] mx-auto w-full">
                {children}
              </div>
            </div>
          </div>
        </div>
      </SidebarProvider>
    </SWRConfig>
  )
}
