'use client'
import { useState, useEffect } from 'react'
import { cn } from '@/app/dashboard/lib/utils'

import {
    Sidebar,
    SidebarContent,
    SidebarFooter,
    SidebarHeader,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    SidebarRail,
    useSidebar,
} from '@/components/animate-ui/components/radix/sidebar'
import {
    LayoutDashboard,
    Briefcase,
    FileText,
    Users,
    BarChart,
    UserCheck,
    PanelLeft,
    LogOut,
    LifeBuoy,
    CheckCircle2,
    Settings,
    Activity,
    Database,
} from 'lucide-react'
import {
    Avatar,
    AvatarFallback,
    AvatarImage,
} from '@/components/ui/avatar'
import { useAuth } from '@/app/dashboard/lib/auth-context'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import useSWR from 'swr'
import { fetcher } from '@/app/dashboard/lib/swr-fetcher'
import { APIClient } from '@/app/dashboard/lib/api-client'

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
    const { user, logout } = useAuth()
    const pathname = usePathname()
    const { toggleSidebar, state } = useSidebar()

    const { data: pendingApps } = useSWR<{ count: number }>(
        user?.role === 'hr' ? '/api/applications/pending-count' : null,
        (url: string) => fetcher<{ count: number }>(url),
        {
            refreshInterval: 300000, // 5 min — badge counts don't need real-time updates
            dedupingInterval: 60000,
            revalidateOnFocus: false,
            revalidateOnReconnect: false,
        },
    )

    // Use SWR for ticket count
    const { data: ticketData } = useSWR<{ count: number }>(
        user?.role === 'hr' ? '/api/tickets/count' : null,
        (url: string) => fetcher<{ count: number }>(url),
        {
            refreshInterval: 180000, // 3 min — ticket count badge
            dedupingInterval: 60000,
            revalidateOnFocus: false,
            revalidateOnReconnect: false,
        }
    )

    const pendingCount = pendingApps?.count ?? 0
    const ticketCount = ticketData?.count || 0

    const { data: settings } = useSWR('/api/settings', (url) => APIClient.get(url)) as { data: any }
    const companyLogo = settings?.company_logo_url || null



    // Get initials for avatar fallback
    const initials = user?.full_name
        ? user.full_name
            .split(' ')
            .map((n) => n[0])
            .join('')
            .toUpperCase()
            .slice(0, 2)
        : 'U'

    // Determine navigation links based on user role
    const links = [
        { href: '/dashboard/hr', label: 'Dashboard', icon: LayoutDashboard },
        { href: '/dashboard/hr/jobs', label: 'Job Postings', icon: Briefcase },
        { href: '/dashboard/hr/applications', label: 'Applications', icon: Users },
        { href: '/dashboard/hr/pipeline', label: 'Hiring Pipeline', icon: UserCheck },
        { href: '/dashboard/hr/reports', label: 'Reports', icon: BarChart },
        { href: '/dashboard/hr/tickets', label: 'Tickets', icon: LifeBuoy },
        { href: '/dashboard/hr/batch-analysis', label: 'Batch Analysis', icon: FileText },
        { href: '/dashboard/onboarding', label: 'Onboarding', icon: CheckCircle2 },
        { href: '/dashboard/repository', label: 'Repository', icon: Database },
        { href: '/dashboard/settings', label: 'Settings', icon: Settings },
    ]

    if (user?.role === 'super_admin') {
        links.splice(3, 0, { href: '/dashboard/hr/approvals', label: 'HR Management', icon: UserCheck })
        // links.splice(links.length - 1, 0, { href: '/dashboard/reliability', label: 'Reliability', icon: Activity })
    }

    return (
        <Sidebar collapsible="icon" {...props} className="border-r border-sidebar-border bg-sidebar/80 backdrop-blur-xl text-sidebar-foreground shadow-xl transition-colors duration-300">
            <SidebarHeader className="border-b border-sidebar-border px-4 py-6">
                <div className="flex items-center justify-between group-data-[collapsible=icon]:justify-center">
                    {/* User Profile Info */}
                    <div className="flex items-center gap-3 overflow-hidden group-data-[collapsible=icon]:hidden">
                        <Avatar className="h-10 w-10 border-2 border-sidebar-primary/20 shadow-sm ring-2 ring-sidebar-ring/50">
                            <AvatarImage
                                src={companyLogo || user?.profile_image_url || `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(user?.email || user?.role || 'default')}`}
                                alt={user?.full_name || 'User avatar'}
                                className="bg-background object-cover"
                            />
                            <AvatarFallback className="bg-gradient-to-br from-primary to-accent text-primary-foreground font-bold">
                                {companyLogo ? (
                                    <img src={companyLogo} className="h-full w-full object-contain" alt="Logo Fallback" />
                                ) : initials}
                            </AvatarFallback>
                        </Avatar>
                        <div className="flex flex-col">
                            <span className="font-bold text-sm text-sidebar-foreground truncate max-w-[120px]">
                                {user?.full_name}
                            </span>
                            <span className="text-xs text-muted-foreground truncate max-w-[120px]">
                                HR Manager
                            </span>
                        </div>
                    </div>

                    {/* Collapse Button - hidden in mobile, shown in desktop */}
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={toggleSidebar}
                        className="h-8 w-8 text-muted-foreground hover:text-sidebar-primary hover:bg-sidebar-accent rounded-full transition-colors group-data-[collapsible=icon]:rotate-180"
                    >
                        <PanelLeft className="h-4 w-4" />
                    </Button>
                </div>
            </SidebarHeader>

            <SidebarContent className="px-3 py-4">
                <SidebarMenu className="gap-1">
                    {links.map((link) => {
                        const Icon = link.icon
                        // Robust matching for dashboard routes (handles sub-routes and singular/plural variants)
                        const isActive = pathname === link.href || 
                                       (link.href !== '/dashboard/hr' && pathname.startsWith(link.href)) ||
                                       (link.href.includes('pipeline') && pathname.includes('pipeline'))

                        return (
                            <SidebarMenuItem key={link.href}>
                                <SidebarMenuButton
                                    asChild
                                    isActive={isActive}
                                    tooltip={link.label}
                                    className={cn(
                                        "relative gap-3 rounded-lg transition-all duration-200 group/item",
                                        "text-sidebar-foreground hover:bg-sidebar-accent/30",
                                        isActive && "bg-sidebar-accent/60 text-primary font-bold shadow-sm"
                                    )}
                                >
                                    <Link href={link.href} className="flex items-center justify-between w-full">
                                        {isActive && (
                                            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1.5 h-8 bg-primary rounded-r-lg z-20" />
                                        )}
                                        <div className="flex items-center gap-3">
                                            <Icon className={cn(
                                                "h-5 w-5 shrink-0 transition-colors",
                                                isActive ? "text-primary" : "text-muted-foreground group-hover/item:text-sidebar-foreground"
                                            )} />
                                            <span className={cn(
                                                "group-data-[collapsible=icon]:hidden transition-colors",
                                                isActive ? "text-primary" : "text-sidebar-foreground"
                                            )}>
                                                {link.label}
                                            </span>
                                        </div>
                                        {link.label === 'Applications' && pendingCount > 0 && (
                                            <Badge
                                                variant="secondary"
                                                className="ml-auto h-5 min-w-5 flex items-center justify-center rounded-full px-1 text-[10px] font-bold bg-primary text-primary-foreground group-data-[collapsible=icon]:hidden"
                                            >
                                                {pendingCount}
                                            </Badge>
                                        )}
                                            {link.label === 'Tickets' && ticketCount > 0 && (
                                            <Badge
                                                variant="secondary"
                                                className="ml-auto h-5 min-w-5 flex items-center justify-center rounded-full px-1 text-[10px] font-bold bg-destructive text-destructive-foreground animate-pulse group-data-[collapsible=icon]:hidden"
                                            >
                                                {ticketCount}
                                            </Badge>
                                        )}
                                    </Link>
                                </SidebarMenuButton>
                            </SidebarMenuItem>
                        )
                    })}
                </SidebarMenu>
            </SidebarContent>

            <SidebarFooter className="border-t border-sidebar-border p-4">
                <SidebarMenu>
                    <SidebarMenuItem>
                        <SidebarMenuButton
                            onClick={logout}
                            tooltip="Sign Out"
                            className="flex-1 gap-3 rounded-xl text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                        >
                            <LogOut className="h-5 w-5 shrink-0" />
                            <span className="group-data-[collapsible=icon]:hidden">
                                Sign Out
                            </span>
                        </SidebarMenuButton>
                    </SidebarMenuItem>
                </SidebarMenu>
            </SidebarFooter>

            <SidebarRail />
        </Sidebar>
    )
}
