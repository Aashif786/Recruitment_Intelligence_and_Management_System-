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
        try {
            await APIClient.put(`/api/notifications/${id}/read`, {})
            mutate(prev =>
                prev?.map(n => n.id === id ? { ...n, is_read: true } : n),
                false
            )
        } catch {
            // Silently fail
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
            <PopoverContent className="w-[380px] p-0 shadow-2xl border-primary/20 overflow-hidden rounded-2xl" align="end" sideOffset={8}>
                <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
                    <h4 className="font-semibold text-sm">Notifications</h4>
                    {unreadCount > 0 && (
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-medium text-primary bg-primary/10 px-2 py-1 rounded-md">
                                {unreadCount} new
                            </span>
                            <Button 
                                variant="ghost" 
                                size="sm" 
                                onClick={markAllAsRead}
                                className="text-[10px] h-7 font-bold text-muted-foreground hover:text-primary hover:bg-primary/5 px-2"
                            >
                                Mark all as read
                            </Button>
                        </div>
                    )}
                </div>
                <ScrollArea className={cn(notificationsArray.length > 0 ? "h-[450px]" : "h-auto")}>
                    {notificationsArray.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
                            <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
                                <Bell className="h-6 w-6 text-muted-foreground/40" />
                            </div>
                            <p className="text-sm font-semibold text-foreground">No new notifications</p>
                            <p className="text-xs text-muted-foreground mt-1">We'll alert you when something happens.</p>
                        </div>
                    ) : (
                        <div className="flex flex-col">
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
                                        "w-full text-left p-4 hover:bg-muted/80 transition-all border-l-4 group flex items-start gap-4 border-b border-border last:border-b-0",
                                        !n.is_read ? 'bg-primary/[0.03] border-l-primary' : 'bg-background border-l-transparent'
                                    )}
                                >
                                    <div className="flex-1 min-w-0 pr-4 relative">
                                        <div className="flex justify-between items-start mb-1">
                                            <p className={cn(
                                                "text-sm truncate pr-2",
                                                !n.is_read ? 'font-semibold text-foreground' : 'font-medium text-muted-foreground'
                                            )}>
                                                {n.title}
                                            </p>
                                            <span className="text-[10px] text-muted-foreground/60 whitespace-nowrap mt-0.5">
                                                {new Date(n.created_at).toLocaleDateString()}
                                            </span>
                                        </div>
                                        <p className={cn(
                                            "text-xs line-clamp-2",
                                            !n.is_read ? 'text-foreground/80' : 'text-muted-foreground/80'
                                        )}>
                                            {n.message}
                                        </p>

                                        {n.related_application_id && (
                                            <div className={cn(
                                                "absolute top-1/2 -translate-y-1/2 -right-2 transition-all duration-200",
                                                !n.is_read ? 'opacity-100 translate-x-0 cursor-pointer text-primary' : 'opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 cursor-pointer text-muted-foreground'
                                            )}>
                                                <ChevronRight className="h-4 w-4" />
                                            </div>
                                        )}
                                    </div>
                                    {!n.is_read && (
                                        <span className="h-2 w-2 rounded-full bg-primary shrink-0 mt-1.5 shadow-sm shadow-primary/40 block" />
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
