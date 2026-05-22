'use client'

import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
    DialogDescription,
} from '@/components/ui/dialog'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { APIClient } from '@/app/dashboard/lib/api-client'
import { toast } from 'sonner'
import { PageHeader } from '@/components/page-header'
import useSWR from 'swr'
import { fetcher } from '@/app/dashboard/lib/swr-fetcher'
import { useRouter } from 'next/navigation'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    Mail,
    Inbox,
    ChevronLeft,
    ChevronRight,
    Loader2,
    CheckCircle2,
    AlertTriangle,
    Download,
    Search,
    RefreshCw,
    FileText,
    ExternalLink,
    Settings,
    Save,
    Zap,
} from 'lucide-react'
import { Switch } from '@/components/ui/switch'

interface IngestedEmail {
    id: number
    sender_email: string
    subject: string
    file_name: string
    file_url: string | null
    received_at: string
    processed: boolean
    application_id: number | null
    job_title: string | null
    job_code: string | null
    is_duplicate: boolean
}

interface PaginatedResponse {
    items: IngestedEmail[]
    total: number
    page: number
    size: number
    pages: number
}

export default function IngestedEmailsPage() {
    const router = useRouter()
    const [page, setPage] = useState(1)
    const [pageSize, setPageSize] = useState(10)
    const [searchTerm, setSearchTerm] = useState('')
    const [debouncedSearch, setDebouncedSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState('all') // all, mapped, unmapped
    const [isSyncing, setIsSyncing] = useState(false)
    const [isAssigning, setIsAssigning] = useState(false)
    const [isSavingSettings, setIsSavingSettings] = useState(false)
    
    // IMAP Sync credentials (defaults to verified credentials)
    const [imapUser, setImapUser] = useState('caldiminternship@gmail.com')
    const [imapPass, setImapPass] = useState('jaesbucnsfnlediv')
    const [autoSyncEnabled, setAutoSyncEnabled] = useState(false)
    const [showCredentials, setShowCredentials] = useState(false)

    // Load current settings on mount
    useEffect(() => {
        const loadSettings = async () => {
            try {
                const settings = await APIClient.get('/api/settings') as any
                if (settings.imap_email) setImapUser(settings.imap_email)
                if (settings.imap_password) setImapPass(settings.imap_password)
                setAutoSyncEnabled(!!settings.auto_sync_enabled)
            } catch (err) {
                console.error('Failed to load settings:', err)
            }
        }
        loadSettings()
    }, [])

    // Assignment Modal State
    const [selectedResume, setSelectedResume] = useState<IngestedEmail | null>(null)
    const [targetJobId, setTargetJobId] = useState<string>('')

    // Debounce search
    useEffect(() => {
        const handler = setTimeout(() => {
            setDebouncedSearch(searchTerm)
            setPage(1)
        }, 400)
        return () => clearTimeout(handler)
    }, [searchTerm])

    // Load open jobs for manual assignment dropdown
    const { data: jobs } = useSWR<any[]>('/api/jobs', fetcher)
    const openJobs = useMemo(() => {
        return (jobs || []).filter(job => job.status === 'open')
    }, [jobs])

    // API URL construction
    const listUrl = useMemo(() => {
        const q = new URLSearchParams()
        q.set('limit', String(pageSize))
        q.set('skip', String((page - 1) * pageSize))
        if (debouncedSearch) q.set('search', debouncedSearch)
        if (statusFilter === 'mapped') q.set('processed', 'true')
        if (statusFilter === 'unmapped') q.set('processed', 'false')
        return `/api/applications/ingested-emails?${q.toString()}`
    }, [page, pageSize, debouncedSearch, statusFilter])

    const { data, error, isLoading, mutate } = useSWR<PaginatedResponse>(listUrl, fetcher, {
        keepPreviousData: true,
        refreshInterval: 60000 // refresh every minute
    })

    const allItems = data?.items ?? []
    
    const filteredItems = allItems;

    const totalCount = data?.total ?? 0;
    const totalPages = data?.pages ?? 0;

    // Save IMAP Settings
    const handleSaveSettings = async () => {
        if (!imapUser.trim() || !imapPass.trim()) {
            toast.error('Please enter both IMAP Email and App Password')
            return
        }

        setIsSavingSettings(true)
        const toastId = toast.loading('Saving recruiter mailbox configuration...')

        try {
            await APIClient.post('/api/settings', {
                imap_email: imapUser.trim(),
                imap_password: imapPass.trim(),
                auto_sync_enabled: autoSyncEnabled
            })

            toast.success('Configuration saved! Auto-sync will now run in the background.', { id: toastId })
            setShowCredentials(false)
        } catch (err: any) {
            console.error('Save settings error:', err)
            toast.error(err.response?.data?.detail || 'Failed to save settings.', { id: toastId })
        } finally {
            setIsSavingSettings(false)
        }
    }

    // Trigger Manual Email Ingestion via API
    const handleSync = async () => {
        if (!imapUser.trim() || !imapPass.trim()) {
            toast.error('Please enter both IMAP Email and App Password')
            return
        }

        setIsSyncing(true)
        const toastId = toast.loading('Connecting to mailbox and fetching resumes...')

        try {
            const res = (await APIClient.post('/api/applications/ingest-emails', {
                imap_user: imapUser.trim(),
                imap_pass: imapPass.trim()
            })) as any

            if (res.saved_count > 0) {
                toast.success(
                    `Found ${res.saved_count} new resumes! AI mapping and analysis has started in the background.`,
                    { id: toastId, duration: 6000 }
                )
            } else {
                toast.success('Mailbox is up to date. No new resumes found.', { id: toastId })
            }
            
            // Immediately mutate to show the new ingested records (fetch is fast)
            mutate()
            
            // Re-mutate after 10 seconds to show AI mapping results
            setTimeout(() => mutate(), 10000)
            setTimeout(() => mutate(), 30000)
        } catch (err: any) {
            console.error('Sync error:', err)
            toast.error(err.response?.data?.detail || err.message || 'Sync failed. Please verify your IMAP login details.', { id: toastId })
        } finally {
            setIsSyncing(false)
        }
    }

    // Manual Job Assignment Handler
    const handleAssignConfirm = async () => {
        if (!selectedResume || !targetJobId) {
            toast.error('Please select a target job')
            return
        }

        setIsAssigning(true)
        const toastId = toast.loading(`Assigning candidate ${selectedResume.sender_email.split('<')[0]} to selected job...`)

        try {
            await APIClient.post(`/api/applications/ingested-emails/${selectedResume.id}/assign`, {
                job_id: Number(targetJobId)
            })

            toast.success('Successfully assigned! Application created and AI parsing triggered.', { id: toastId })
            setSelectedResume(null)
            setTargetJobId('')
            mutate()
        } catch (err: any) {
            console.error('Assignment error:', err)
            toast.error(err.response?.data?.detail || 'Failed to assign candidate.', { id: toastId })
        } finally {
            setIsAssigning(false)
        }
    }

    const getInitials = (sender: string) => {
        const cleaned = sender.split('<')[0].trim()
        if (!cleaned || cleaned.toLowerCase() === 'emailed candidate') {
            return 'U'
        }
        return cleaned.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    }

    return (
        <div className="space-y-8">
            <PageHeader
                title="Email Ingestion Inbox"
                description="Review, manage, and manually assign job applications fetched automatically from your recruiter email channels."
                icon={Mail}
            >
                <div className="flex items-center gap-4">
                    {autoSyncEnabled && (
                        <Badge variant="outline" className="h-9 px-4 rounded-xl bg-emerald-50 text-emerald-600 border-emerald-100 flex items-center gap-2 animate-pulse font-bold text-[10px] tracking-widest uppercase">
                            <Zap className="h-3 w-3 fill-emerald-600" />
                            Auto-Sync Active
                        </Badge>
                    )}
                    <div className="flex gap-3">
                        <Button
                            variant="outline"
                            onClick={() => setShowCredentials(!showCredentials)}
                            className={`gap-2 border-border shadow-sm rounded-xl h-11 ${showCredentials ? 'bg-primary/5 border-primary/20 text-primary' : ''}`}
                        >
                            <Settings className="h-4 w-4" />
                            Configure Mailbox
                        </Button>
                        <Button
                            onClick={handleSync}
                            disabled={isSyncing}
                            className="gap-2 bg-primary text-primary-foreground shadow-sm rounded-xl h-11 font-semibold active:scale-95 transition-all"
                        >
                            {isSyncing ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <RefreshCw className="h-4 w-4" />
                            )}
                            Sync Emails
                        </Button>
                    </div>
                </div>
            </PageHeader>

            {/* Credentials Card */}
            {showCredentials && (
                <Card className="border-2 border-primary/10 bg-card shadow-xl rounded-2xl animate-in zoom-in-95 slide-in-from-top-4 duration-300">
                    <CardHeader className="border-b border-border/50 pb-6">
                        <div className="flex items-center justify-between">
                            <div className="space-y-1">
                                <CardTitle className="text-lg font-black flex items-center gap-2">
                                    <Settings className="h-5 w-5 text-primary" />
                                    Mailbox Configuration
                                </CardTitle>
                                <CardDescription>
                                    Manage the Gmail IMAP settings used for background application polling.
                                </CardDescription>
                            </div>
                            <div className="flex items-center gap-3 bg-slate-50 p-2.5 rounded-2xl border border-slate-200">
                                <div className="space-y-0.5 px-1">
                                    <Label className="text-[10px] font-black uppercase tracking-tighter text-slate-500">Auto-Syncing</Label>
                                    <p className="text-[9px] text-slate-400 font-medium">Runs every 1 minute</p>
                                </div>
                                <Switch 
                                    checked={autoSyncEnabled} 
                                    onCheckedChange={setAutoSyncEnabled}
                                    className="data-[state=checked]:bg-emerald-500"
                                />
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent className="pt-8 space-y-6">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <Label htmlFor="imap_user" className="text-[10px] font-black uppercase tracking-widest text-muted-foreground ml-1">IMAP Email Address</Label>
                                <Input
                                    id="imap_user"
                                    value={imapUser}
                                    onChange={e => setImapUser(e.target.value)}
                                    className="h-12 bg-background border-2 border-input rounded-xl focus:ring-4 focus:ring-primary/5 focus:border-primary font-medium"
                                    placeholder="example@gmail.com"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="imap_pass" className="text-[10px] font-black uppercase tracking-widest text-muted-foreground ml-1">Gmail App Password</Label>
                                <Input
                                    id="imap_pass"
                                    type="password"
                                    value={imapPass}
                                    onChange={e => setImapPass(e.target.value)}
                                    className="h-12 bg-background border-2 border-input rounded-xl focus:ring-4 focus:ring-primary/5 focus:border-primary font-medium"
                                    placeholder="xxxx xxxx xxxx xxxx"
                                />
                            </div>
                        </div>
                        
                        <div className="pt-2 border-t border-border/50 flex justify-end gap-3">
                             <Button
                                variant="ghost"
                                onClick={() => setShowCredentials(false)}
                                className="h-12 px-6 rounded-xl font-bold text-slate-500"
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={handleSaveSettings}
                                disabled={isSavingSettings}
                                className="h-12 px-8 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-bold shadow-lg shadow-emerald-600/20 gap-2"
                            >
                                {isSavingSettings ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                                Save Configuration
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Quick Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <Card className="border border-border/60 shadow-sm rounded-2xl bg-card">
                    <CardContent className="p-6 flex items-center gap-4">
                        <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center border border-primary/20 shrink-0">
                            <Inbox className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                            <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Total Ingested</div>
                            <div className="text-2xl font-black text-foreground mt-0.5 tabular-nums">
                                {isLoading ? '...' : totalCount}
                            </div>
                        </div>
                    </CardContent>
                </Card>
                
                <Card className="border border-border/60 shadow-sm rounded-2xl bg-card">
                    <CardContent className="p-6 flex items-center gap-4">
                        <div className="h-12 w-12 rounded-xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 shrink-0">
                            <CheckCircle2 className="h-6 w-6 text-emerald-600" />
                        </div>
                        <div>
                            <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Auto-Mapped</div>
                            <div className="text-2xl font-black text-foreground mt-0.5 tabular-nums">
                                {isLoading ? '...' : (statusFilter === 'mapped' ? totalCount : '—')}
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="border border-border/60 shadow-sm rounded-2xl bg-card">
                    <CardContent className="p-6 flex items-center gap-4">
                        <div className="h-12 w-12 rounded-xl bg-amber-500/10 flex items-center justify-center border border-amber-500/20 shrink-0">
                            <AlertTriangle className="h-6 w-6 text-amber-500" />
                        </div>
                        <div>
                            <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Pending Assignment</div>
                            <div className="text-2xl font-black text-foreground mt-0.5 tabular-nums">
                                {isLoading ? '...' : (statusFilter === 'unmapped' ? totalCount : '—')}
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Filters and Toolbar */}
            <div className="bg-card p-4 rounded-2xl border border-border shadow-sm">
                <div className="flex flex-col md:flex-row gap-4 items-center">
                    {/* Search */}
                    <div className="relative flex-1 w-full">
                        <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-muted-foreground h-5 w-5" />
                        <Input
                            type="text"
                            placeholder="Search sender email, subject, or resume name..."
                            value={searchTerm}
                            onChange={e => setSearchTerm(e.target.value)}
                            className="pl-12 h-11 bg-background border-2 border-input rounded-xl focus:ring-4 focus:ring-primary/5 focus:border-primary text-base"
                        />
                    </div>
                    {/* Status Filter */}
                    <div className="w-full md:w-[220px]">
                        <Select value={statusFilter} onValueChange={setStatusFilter}>
                            <SelectTrigger className="h-11 rounded-xl border-2 border-input bg-background font-medium focus:ring-0">
                                <SelectValue placeholder="Filter by Status" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">All Ingested</SelectItem>
                                <SelectItem value="mapped">Auto-Mapped</SelectItem>
                                <SelectItem value="unmapped">Pending Assignment</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>
            </div>

            {/* Data Table */}
            {isLoading ? (
                <div className="text-center py-20 flex flex-col items-center justify-center gap-4 bg-card border border-border rounded-2xl shadow-sm">
                    <Loader2 className="h-10 w-10 animate-spin text-primary" />
                    <p className="text-sm font-bold text-muted-foreground uppercase tracking-widest animate-pulse">Loading Ingestion Box...</p>
                </div>
            ) : filteredItems.length === 0 ? (
                <div className="text-center py-20 bg-card rounded-2xl border border-border shadow-sm flex flex-col items-center justify-center gap-4">
                    <Inbox className="h-12 w-12 text-muted-foreground/45" />
                    <div>
                        <h3 className="font-bold text-lg text-foreground">No ingested resumes found</h3>
                        <p className="text-sm text-muted-foreground mt-1 max-w-sm">
                            Click 'Sync Emails' to connect to your configured recruiter mailbox and fetch applicant resumes.
                        </p>
                    </div>
                </div>
            ) : (
                <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-sm">
                    <Table>
                        <TableHeader className="bg-muted/40">
                            <TableRow>
                                <TableHead className="w-[280px]">Sender / Candidate</TableHead>
                                <TableHead>Email Subject</TableHead>
                                <TableHead className="w-[180px]">Received Date</TableHead>
                                <TableHead className="w-[240px]">Resume File</TableHead>
                                <TableHead className="w-[200px]">Mapping Status</TableHead>
                                <TableHead className="text-right w-[150px]">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {filteredItems.map((item) => {
                                const senderCleaned = item.sender_email.split('<')[0].trim()
                                const emailAddress = item.sender_email.includes('<')
                                    ? item.sender_email.split('<')[1].replace('>', '').trim()
                                    : item.sender_email.trim()

                                return (
                                    <TableRow key={item.id} className="hover:bg-muted/30 transition-colors">
                                        <TableCell className="font-semibold">
                                            <div className="flex items-center gap-3">
                                                <div className="h-9 w-9 rounded-full bg-primary/10 border border-primary/25 flex items-center justify-center text-xs font-bold text-primary shrink-0 shadow-inner">
                                                    {getInitials(item.sender_email)}
                                                </div>
                                                <div className="min-w-0">
                                                    <div className="flex items-center gap-1.5">
                                                        <div className="text-sm font-bold text-foreground truncate max-w-[150px]">{senderCleaned}</div>
                                                        {item.is_duplicate && (
                                                            <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 bg-orange-50 text-orange-600 border-orange-200 font-semibold shrink-0">
                                                                Duplicate
                                                            </Badge>
                                                        )}
                                                    </div>
                                                    <div className="text-xs text-muted-foreground truncate max-w-[180px]">{emailAddress}</div>
                                                </div>
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-sm font-medium text-foreground max-w-[300px] truncate" title={item.subject}>
                                            {item.subject}
                                        </TableCell>
                                        <TableCell className="text-xs text-muted-foreground font-semibold">
                                            {new Date(item.received_at).toLocaleDateString(undefined, {
                                                month: 'short',
                                                day: 'numeric',
                                                year: 'numeric',
                                                hour: '2-digit',
                                                minute: '2-digit'
                                            })}
                                        </TableCell>
                                        <TableCell>
                                            {item.file_url ? (
                                                <a
                                                    href={item.file_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:underline"
                                                >
                                                    <FileText className="h-3.5 w-3.5 text-primary shrink-0" />
                                                    <span className="truncate max-w-[150px]">{item.file_name}</span>
                                                    <ExternalLink className="h-3 w-3" />
                                                </a>
                                            ) : (
                                                <span className="text-xs text-muted-foreground italic">No attachment url</span>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            {item.application_id ? (
                                                <div className="flex flex-col gap-1 items-start">
                                                    <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25 hover:bg-emerald-500/10 font-bold text-[10px] uppercase py-0.5 px-2">
                                                        Auto-Mapped
                                                    </Badge>
                                                    <span className="text-[11px] text-muted-foreground font-bold truncate max-w-[180px]" title={item.job_title || ''}>
                                                        {item.job_title} ({item.job_code})
                                                    </span>
                                                </div>
                                            ) : (
                                                <Badge className="bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/25 hover:bg-amber-500/10 font-bold text-[10px] uppercase py-0.5 px-2 flex items-center gap-1 w-max">
                                                    <AlertTriangle className="h-3 w-3" />
                                                    Pending Assignment
                                                </Badge>
                                            )}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            {item.application_id ? (
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    onClick={() => router.push(`/dashboard/hr/applications/${item.application_id}`)}
                                                    className="h-9 px-3 text-xs font-bold text-primary uppercase tracking-wider hover:bg-primary/10 rounded-xl"
                                                >
                                                    View Candidate
                                                </Button>
                                            ) : (
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() => setSelectedResume(item)}
                                                    className="h-9 px-3 text-xs font-bold text-amber-600 hover:text-amber-700 hover:bg-amber-50 dark:hover:bg-amber-500/10 border-amber-500/30 rounded-xl shadow-none"
                                                >
                                                    Assign to Job
                                                </Button>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                )
                            })}
                        </TableBody>
                    </Table>

                    {/* Pagination */}
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-4 px-6 py-4 border-t border-border bg-muted/20">
                        <div className="text-sm text-muted-foreground font-semibold">
                            Showing <span className="font-bold text-foreground/80">{filteredItems.length}</span> of <span className="font-bold text-foreground/80">{totalCount}</span> ingested records
                        </div>
                        
                        <div className="flex items-center gap-4">
                            <div className="text-xs font-bold text-muted-foreground">
                                Page <span className="text-foreground/80 font-black">{page}</span> of {totalPages || 1}
                            </div>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setPage(p => Math.max(p - 1, 1))}
                                    disabled={page <= 1 || isLoading}
                                    className="h-8 px-3 rounded-lg font-bold border-border bg-background shadow-sm active:scale-95 disabled:opacity-55"
                                >
                                    <ChevronLeft className="h-4 w-4" />
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setPage(p => Math.min(p + 1, totalPages))}
                                    disabled={page >= totalPages || isLoading}
                                    className="h-8 px-3 rounded-lg font-bold border-border bg-background shadow-sm active:scale-95 disabled:opacity-55"
                                >
                                    <ChevronRight className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Manual Assignment Modal */}
            <Dialog open={selectedResume !== null} onOpenChange={(open) => {
                if (!open) {
                    setSelectedResume(null)
                    setTargetJobId('')
                }
            }}>
                <DialogContent className="max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl">
                    <DialogHeader>
                        <DialogTitle className="text-lg font-black text-foreground flex items-center gap-2">
                            <Mail className="h-5 w-5 text-amber-500" />
                            Manually Assign Job Application
                        </DialogTitle>
                        <DialogDescription className="text-sm text-muted-foreground mt-1">
                            Connect this unassigned candidate email to an open active recruitment job posting.
                        </DialogDescription>
                    </DialogHeader>

                    {selectedResume && (
                        <div className="my-5 p-4 rounded-xl bg-muted/50 border border-border space-y-2 text-sm">
                            <div className="flex justify-between">
                                <span className="font-bold text-muted-foreground">Candidate:</span>
                                <span className="font-bold text-foreground truncate max-w-[200px]">{selectedResume.sender_email.split('<')[0]}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="font-bold text-muted-foreground">Email:</span>
                                <span className="font-medium text-foreground truncate max-w-[200px]">{selectedResume.sender_email.includes('<') ? selectedResume.sender_email.split('<')[1].replace('>', '') : selectedResume.sender_email}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="font-bold text-muted-foreground">Resume File:</span>
                                <span className="font-medium text-primary truncate max-w-[200px]">{selectedResume.file_name}</span>
                            </div>
                        </div>
                    )}

                    <div className="space-y-2.5">
                        <Label htmlFor="target_job" className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Select Active Recruitment Job</Label>
                        <Select value={targetJobId} onValueChange={setTargetJobId}>
                            <SelectTrigger id="target_job" className="h-11 rounded-xl border-border bg-background focus:ring-0 text-sm font-semibold">
                                <SelectValue placeholder="Choose an open role..." />
                            </SelectTrigger>
                            <SelectContent>
                                {openJobs.map((job) => (
                                    <SelectItem key={job.id} value={String(job.id)} className="font-semibold text-sm">
                                        {job.title} ({job.job_id})
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {openJobs.length === 0 && (
                            <p className="text-xs text-destructive font-bold flex items-center gap-1 mt-1">
                                <AlertTriangle className="h-3 w-3" />
                                No active open jobs found. Please create an open job first!
                            </p>
                        )}
                    </div>

                    <DialogFooter className="mt-8 flex gap-3 sm:justify-end">
                        <Button
                            variant="ghost"
                            onClick={() => setSelectedResume(null)}
                            className="rounded-xl border border-border font-bold text-muted-foreground h-11"
                        >
                            Cancel
                        </Button>
                        <Button
                            onClick={handleAssignConfirm}
                            disabled={isAssigning || !targetJobId}
                            className="rounded-xl font-bold bg-primary text-primary-foreground hover:opacity-90 h-11 active:scale-95 transition-all gap-2"
                        >
                            {isAssigning ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <CheckCircle2 className="h-4 w-4" />
                            )}
                            Confirm Assignment
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
