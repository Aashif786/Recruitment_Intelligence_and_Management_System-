'use client'

import { useCallback, useMemo } from 'react'

import {
    Avatar,
    AvatarFallback,
    AvatarImage,
} from '@/components/ui/avatar'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuGroup,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/app/dashboard/lib/auth-context'
import { useRouter } from 'next/navigation'
import { LogOut, User as UserIcon, Settings, GitFork, Image as ImageIcon } from 'lucide-react'
import useSWR from 'swr'
import { APIClient } from '@/app/dashboard/lib/api-client'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { toast } from 'sonner'
import { useState } from 'react'

export function UserNav() {
    const { user, logout } = useAuth()
    const router = useRouter()

    const handleLogout = useCallback(() => {
        logout()
    }, [logout])

    const [isLogoDialogOpen, setIsLogoDialogOpen] = useState(false)
    const [logoUrl, setLogoUrl] = useState('')
    const [isUpdating, setIsUpdating] = useState(false)

    // Memoized initials for efficiency
    const initials = useMemo(() => {
        if (!user?.full_name) return 'U'
        return user.full_name
            .trim()
            .split(/\s+/)
            .map((n) => n[0])
            .join('')
            .toUpperCase()
            .slice(0, 2)
    }, [user?.full_name])

    const { data: settings, mutate } = useSWR('/api/settings', (url) => APIClient.get(url)) as { data: any, mutate: any }

    const avatarUrl = useMemo(() => {
        if (settings?.company_logo_url) return settings.company_logo_url
        if (user?.profile_image_url) return user.profile_image_url
        return `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(user?.email || 'default')}`
    }, [user?.profile_image_url, user?.email, settings?.company_logo_url])

    const handleUpdateLogo = async () => {
        if (!logoUrl.trim()) {
            toast.error("Please enter a valid URL")
            return
        }
        setIsUpdating(true)
        try {
            await APIClient.post('/api/settings', { company_logo_url: logoUrl })
            toast.success("Brand logo updated successfully")
            setIsLogoDialogOpen(false)
            // Trigger SWR revalidation
            mutate('/api/settings')
        } catch (error) {
            toast.error("Failed to update logo")
        } finally {
            setIsUpdating(false)
        }
    }

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="relative h-10 w-10 rounded-full hover:bg-slate-800/10 transition-all focus-visible:ring-offset-0 focus-visible:ring-0">
                    <Avatar className="h-10 w-10 overflow-hidden">
                        <AvatarImage 
                            src={avatarUrl} 
                            alt={user?.full_name || 'User'} 
                            className="bg-background object-cover"
                        />
                        <AvatarFallback className="bg-transparent font-bold animate-in fade-in duration-500 overflow-hidden">
                            {settings?.company_logo_url ? (
                                <img src={settings.company_logo_url} className="h-full w-full object-contain" alt="Logo Fallback" />
                            ) : (
                                <div className="h-full w-full flex items-center justify-center bg-primary/10 text-primary">
                                    {initials}
                                </div>
                            )}
                        </AvatarFallback>
                    </Avatar>
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-64" align="end" sideOffset={8} forceMount>
                <DropdownMenuLabel className="font-normal">
                    <div className="flex flex-col space-y-1.5 p-1">
                        <p className="text-sm font-semibold leading-none tracking-tight">{user?.full_name || 'User'}</p>
                        <p className="text-xs leading-none text-muted-foreground/80 truncate">
                            {user?.email || 'user@example.com'}
                        </p>
                    </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator className="opacity-50" />
                <DropdownMenuGroup>
                    <DropdownMenuItem className="cursor-pointer py-2.5 focus:bg-accent/40" onClick={() => router.push('/dashboard/settings')}>
                        <Settings className="mr-3 h-4 w-4 text-muted-foreground" />
                        <span>Settings</span>
                    </DropdownMenuItem>
                    {(user?.role === 'hr' || user?.role === 'super_admin') && (
                        <DropdownMenuItem 
                            className="cursor-pointer py-2.5 focus:bg-accent/40" 
                            onClick={() => {
                                setLogoUrl(settings?.company_logo_url || '')
                                setIsLogoDialogOpen(true)
                            }}
                        >
                            <ImageIcon className="mr-3 h-4 w-4 text-muted-foreground" />
                            <span>Update Brand Logo</span>
                        </DropdownMenuItem>
                    )}
                    <DropdownMenuItem className="cursor-pointer py-2.5 focus:bg-accent/40" onClick={() => router.push('/dashboard/repository')}>
                        <GitFork className="mr-3 h-4 w-4 text-muted-foreground" />
                        <span>Repository</span>
                    </DropdownMenuItem>
                </DropdownMenuGroup>
                <DropdownMenuSeparator className="opacity-50" />
                <DropdownMenuItem 
                    onClick={handleLogout} 
                    className="text-destructive focus:text-destructive focus:bg-destructive/5 cursor-pointer py-2.5"
                >
                    <LogOut className="mr-3 h-4 w-4" />
                    <span>Log out</span>
                </DropdownMenuItem>
            </DropdownMenuContent>

            <Dialog open={isLogoDialogOpen} onOpenChange={setIsLogoDialogOpen}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>Update Brand Logo</DialogTitle>
                        <DialogDescription>
                            Provide a direct URL to your company logo (PNG, SVG, or JPG).
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="logo-url">Logo URL</Label>
                            <Input
                                id="logo-url"
                                placeholder="https://example.com/logo.png"
                                value={logoUrl}
                                onChange={(e) => setLogoUrl(e.target.value)}
                            />
                        </div>
                        {logoUrl && (
                            <div className="flex flex-col items-center gap-2 p-4 border rounded-lg bg-muted/20">
                                <span className="text-[10px] uppercase font-bold text-muted-foreground">Preview</span>
                                <img 
                                    src={logoUrl} 
                                    alt="Preview" 
                                    className="h-16 w-auto object-contain"
                                    onError={(e) => (e.currentTarget.style.display = 'none')}
                                />
                            </div>
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setIsLogoDialogOpen(false)}>Cancel</Button>
                        <Button onClick={handleUpdateLogo} disabled={isUpdating}>
                            {isUpdating ? "Updating..." : "Save Changes"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </DropdownMenu>
    )
}
