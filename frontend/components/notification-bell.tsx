'use client'

import React, { useEffect, useState, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { APIClient } from '@/app/dashboard/lib/api-client'
import { useAuth } from '@/app/dashboard/lib/auth-context'
import useSWR, { mutate as globalMutate } from 'swr'
import { fetcher } from '@/app/dashboard/lib/swr-fetcher'
import { cn } from '@/app/dashboard/lib/utils'

import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Bell, ChevronRight } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'

interface Notification {
    id: number
    notification_type: string
    title: string
    message: string
    is_read: boolean
    related_application_id?: number
    created_at: string
}

function formatNotificationDate(dateStr: string) {
    try {
        const date = new Date(dateStr)
        const now = new Date()
        const diffMs = now.getTime() - date.getTime()
        const diffMins = Math.floor(diffMs / 60000)
        const diffHours = Math.floor(diffMins / 60)
        const diffDays = Math.floor(diffHours / 24)

        if (diffMins < 1) return 'Just now'
        if (diffMins < 60) return `${diffMins}m ago`
        if (diffHours < 24) return `${diffHours}h ago`
        if (diffDays === 1) return 'Yesterday'
        if (diffDays < 7) return `${diffDays}d ago`
        
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    } catch {
        return ''
    }
}

export function NotificationBell() {
    const { user } = useAuth()
    const router = useRouter()
    const [isOpen, setIsOpen] = useState(false)
    const canViewNotifications = ['super_admin', 'hr'].includes(user?.role || '')

    const { data: notifications = [], mutate } = useSWR<Notification[]>(
        canViewNotifications ? '/api/notifications?limit=50' : null,
        (url: string) => fetcher<Notification[]>(url),
        {
            refreshInterval: 300000,
            dedupingInterval: 60000,
            revalidateOnFocus: false,
            revalidateOnReconnect: false,
        }
    )

    const markAsRead = useCallback(async (id: number) => {
        // Instantly update the local SWR cache (optimistic update)
        mutate(prev =>
            prev?.map(n => n.id === id ? { ...n, is_read: true } : n),
            false
        )

        try {
            await APIClient.put(`/api/notifications/${id}/read`, {})
            mutate() // Background revalidation to sync with the server
        } catch {
            mutate() // Revert local cache on failure
        }
    }, [mutate])

    const notificationsArray = Array.isArray(notifications) ? notifications : []
    const unreadCount = useMemo(() => notificationsArray.filter(n => !n.is_read).length, [notificationsArray])

    const markAllAsRead = useCallback(async () => {
        const unreadIds = notificationsArray.filter(n => !n.is_read).map(n => n.id)
        if (unreadIds.length === 0) return

        try {
            mutate(prev => prev?.map(n => ({ ...n, is_read: true })), false)
            await Promise.all(unreadIds.map(id => APIClient.put(`/api/notifications/${id}/read`, {})))
            mutate()
        } catch {
            mutate()
        }
    }, [notificationsArray, mutate])

    const sortedNotifications = [...notificationsArray].sort((a, b) => {
        if (a.is_read !== b.is_read) return a.is_read ? 1 : -1
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })

    if (!canViewNotifications) return null

    return (
        <Popover open={isOpen} onOpenChange={setIsOpen}>
            <PopoverTrigger asChild>
                <Button variant="ghost" size="icon" className="relative h-10 w-10 rounded-full text-slate-500 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white hover:bg-muted/50">
                    <Bell className="h-5 w-5" />
                    {unreadCount > 0 && (
                        <span 
                            key={unreadCount} 
                            className="absolute -top-1 -right-1 flex min-w-[18px] h-[18px] px-1 items-center justify-center rounded-full bg-destructive text-[9px] font-black text-destructive-foreground ring-2 ring-background animate-in zoom-in duration-300 pointer-events-none shadow-sm"
                        >
                            {unreadCount}
                        </span>
                    )}
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[410px] p-0 shadow-2xl border border-slate-100 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md overflow-hidden rounded-2xl" align="end" sideOffset={8}>
                <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
                    <h4 className="font-bold text-sm text-slate-800 dark:text-slate-200">Notifications</h4>
                    {unreadCount > 0 && (
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-black text-primary bg-primary/10 px-2.5 py-0.5 rounded-full">
                                {unreadCount} new
                            </span>
                            <Button 
                                variant="ghost" 
                                size="sm" 
                                onClick={markAllAsRead}
                                className="text-[10px] h-7 font-black text-slate-500 hover:text-primary hover:bg-primary/5 px-2 rounded-lg"
                            >
                                Mark all as read
                            </Button>
                        </div>
                    )}
                </div>
                <ScrollArea className={cn(notificationsArray.length > 0 ? "h-[450px]" : "h-auto")}>
                    {notificationsArray.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
                            <div className="w-12 h-12 rounded-full bg-slate-50 dark:bg-slate-800 flex items-center justify-center mb-4">
                                <Bell className="h-6 w-6 text-slate-400 dark:text-slate-500" />
                            </div>
                            <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">No new notifications</p>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">We'll alert you when something happens.</p>
                        </div>
                    ) : (
                        <div className="flex flex-col w-[408px]">
                            {sortedNotifications.map(n => (
                                <button
                                    key={n.id}
                                    onClick={() => {
                                        if (!n.is_read) markAsRead(n.id)
                                        if (n.related_application_id) {
                                            router.push(`/dashboard/hr/applications/${n.related_application_id}`)
                                            setIsOpen(false)
                                        }
                                    }}
                                    className={cn(
                                        "w-full text-left pl-4 py-4 pr-8 hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-all border-l-4 group border-b border-slate-100 dark:border-slate-800 last:border-b-0 relative",
                                        !n.is_read 
                                            ? 'bg-slate-50/60 dark:bg-slate-800/40 border-l-primary' 
                                            : 'bg-transparent border-l-transparent'
                                    )}
                                >
                                    <div className="flex-1 min-w-0 pr-2 relative">
                                        <div className="flex items-center justify-between gap-3 mb-1">
                                            <p className={cn(
                                                "text-sm truncate flex-1 min-w-0 pr-1",
                                                !n.is_read 
                                                    ? 'font-bold text-slate-900 dark:text-slate-100' 
                                                    : 'font-normal text-slate-400 dark:text-slate-500'
                                            )}>
                                                {n.title}
                                            </p>
                                            <span className="text-[10px] font-black text-slate-400/80 whitespace-nowrap shrink-0">
                                                {formatNotificationDate(n.created_at)}
                                            </span>
                                        </div>
                                        <p className={cn(
                                            "text-xs line-clamp-2 leading-relaxed pr-2",
                                            !n.is_read 
                                                ? 'text-slate-600 dark:text-slate-300 font-medium' 
                                                : 'text-slate-400/80 dark:text-slate-500/80 font-normal'
                                        )}>
                                            {n.message}
                                        </p>

                                        {n.related_application_id && (
                                            <div className={cn(
                                                "absolute top-1/2 -translate-y-1/2 -right-4 transition-all duration-200 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 text-slate-400 dark:text-slate-500"
                                            )}>
                                                <ChevronRight className="h-4 w-4" />
                                            </div>
                                        )}
                                    </div>
                                    {!n.is_read && (
                                        <span className="absolute right-3.5 top-[22px] h-2 w-2 rounded-full bg-primary shadow-sm shadow-primary/40 block animate-pulse shrink-0" />
                                    )}
                                </button>
                            ))}
                        </div>
                    )}
                </ScrollArea>
            </PopoverContent>
        </Popover>
    )
}
