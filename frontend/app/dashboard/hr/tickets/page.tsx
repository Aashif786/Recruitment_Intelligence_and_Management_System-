'use client'

import React, { useState, useEffect } from 'react'
import useSWR from 'swr'
import { performMutation } from '@/app/dashboard/lib/swr-utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import {
    LifeBuoy,
    Clock,
    User,
    Mail,
    AlertCircle,
    CheckCircle2,
    XCircle,
    RotateCcw,
    MessageSquare,
    Send,
    Star
} from 'lucide-react'
import { Switch } from "@/components/ui/switch"
import Link from 'next/link'
import { APIClient } from '@/app/dashboard/lib/api-client'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { PageHeader } from '@/components/page-header'
import { Textarea } from "@/components/ui/textarea"
import { toast } from "sonner"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface Ticket {
    id: number
    interview_id: number | null
    application_id: number | null
    test_id: string | null
    job_id: number | null
    job_identifier: string | null
    candidate_name: string
    candidate_email: string
    issue_type: string
    description: string
    status: 'pending' | 'resolved' | 'dismissed'
    hr_response: string | null
    is_reissue_granted: boolean
    created_at: string
    resolved_at: string | null
}

interface Feedback {
    id: number
    interview_id: number
    candidate_name: string
    candidate_email: string
    job_title: string
    job_id: number | null
    ui_ux_rating: number
    feedback_text: string | null
    created_at: string
}


export default function HRTicketsPage() {
    const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null)
    const [hrResponse, setHrResponse] = useState('')
    const [isResolving, setIsResolving] = useState(false)
    const [filter, setFilter] = useState<'pending' | 'all' | 'feedback'>('pending')
    const [sendEmail, setSendEmail] = useState(true)
    const [currentPage, setCurrentPage] = useState(1)
    const [pageSize, setPageSize] = useState(10)

    // Reset page when filter changes
    useEffect(() => { setCurrentPage(1) }, [filter])

    const endpoint = filter === 'feedback' 
        ? `/api/tickets/feedback?limit=${pageSize}&skip=${(currentPage - 1) * pageSize}` 
        : `/api/tickets?status=${filter}&limit=${pageSize}&skip=${(currentPage - 1) * pageSize}`
    const { data: resp, isLoading, mutate } = useSWR<any>(endpoint)
    
    const tickets = (filter === 'feedback' ? [] : (resp?.items || [])) as Ticket[]
    const feedbacks = (filter === 'feedback' ? (resp?.items || []) : []) as Feedback[]



    const handleResolve = async (ticketId: number, action: 'reissue_key' | 'resolve' | 'dismissed' | 'reply') => {
        if (!hrResponse.trim() && action === 'reply') {
            toast.error("Please type a response message before sending a reply.")
            return
        }

        const actionFn = () => APIClient.put(`/api/tickets/${ticketId}/resolve`, {
            hr_response: hrResponse,
            action,
            send_email: sendEmail
        })

        const successMsgs: Record<string, string> = {
            reissue_key: '🔑 Interview key re-issued — candidate can retake.',
            reply: '✉️ Reply sent to candidate.',
            resolve: '✅ Ticket resolved.',
            dismissed: '🚫 Ticket dismissed.',
        }

        setIsResolving(true)
        try {
            await performMutation<any>(
                endpoint,          // ← use exact SWR key so the cache actually refreshes
                mutate,
                actionFn,
                {
                    lockKey: `ticket-${ticketId}`,
                    optimisticData: (current) => {
                        const data = current || { items: [], total: 0 }
                        if (action === 'reply' && filter === 'pending') {
                            return {
                                ...data,
                                items: data.items.map((t: Ticket) =>
                                    t.id === ticketId ? { ...t, hr_response: hrResponse || t.hr_response } : t
                                )
                            }
                        }
                        if (filter === 'pending') {
                            const newItems = data.items.filter((t: Ticket) => t.id !== ticketId)
                            return { ...data, items: newItems, total: data.total - 1 }
                        }
                        return {
                            ...data,
                            items: data.items.map((t: Ticket) =>
                                t.id === ticketId
                                    ? { ...t, status: action === 'dismissed' ? 'dismissed' : action === 'reply' ? 'pending' : 'resolved', hr_response: hrResponse || t.hr_response }
                                    : t
                            )
                        }
                    },
                    successMessage: successMsgs[action] || 'Done.',
                    // Invalidate sidebar badge + analytics
                    invalidateKeys: ['/api/tickets/count', '/api/analytics/dashboard']
                }
            )
            setSelectedTicket(null)
            setHrResponse('')
        } finally {
            setIsResolving(false)
        }
    }

    const getIssueTypeBadge = (type: string) => {
        switch (type) {
            case 'interruption': return 'bg-amber-100 text-amber-700 border-amber-200'
            case 'technical': return 'bg-blue-100 text-blue-700 border-blue-200'
            case 'misconduct_appeal': return 'bg-purple-100 text-purple-700 border-purple-200'
            default: return 'bg-slate-100 text-slate-700'
        }
    }

    return (
        <div className="w-full max-w-[1600px] mx-auto space-y-8 animate-in fade-in duration-700">
            <PageHeader
                title="Support Tickets"
                description="Manage candidate issues and interruption reports."
                icon={LifeBuoy}
            >
                <div className="flex bg-muted p-1 rounded-xl border border-border/50">
                    <Button
                        variant={filter === 'pending' ? 'default' : 'ghost'}
                        size="sm"
                        onClick={() => setFilter('pending')}
                        className="rounded-lg font-bold"
                    >
                        Pending
                    </Button>
                    <Button
                        variant={filter === 'all' ? 'default' : 'ghost'}
                        size="sm"
                        onClick={() => setFilter('all')}
                        className="rounded-lg font-bold"
                    >
                        All History
                    </Button>
                    <Button
                        variant={filter === 'feedback' ? 'default' : 'ghost'}
                        size="sm"
                        onClick={() => setFilter('feedback')}
                        className="rounded-lg font-bold"
                    >
                        Feedback
                    </Button>
                </div>
            </PageHeader>

            {isLoading ? (
                <div className="flex justify-center py-20">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
                </div>
            ) : (filter !== 'feedback' && tickets.length === 0) || (filter === 'feedback' && feedbacks.length === 0) ? (
                <Card className="border-dashed py-20 bg-card/50">
                    <CardContent className="flex flex-col items-center justify-center text-center space-y-4">
                        <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
                            <CheckCircle2 className="h-8 w-8 text-primary" />
                        </div>
                        <div className="space-y-1">
                            <h3 className="text-xl font-bold">All clear!</h3>
                            <p className="text-muted-foreground">{filter === 'feedback' ? 'No candidate feedback available.' : 'No pending support tickets at the moment.'}</p>
                        </div>
                    </CardContent>
                </Card>
            ) : filter === 'feedback' ? (
                <div className="bg-card rounded-2xl border border-border overflow-hidden shadow-sm">
                    {/* List Header */}
                    <div className="grid grid-cols-12 gap-4 px-6 py-3 bg-muted/50 border-b border-border text-xs uppercase tracking-widest font-black text-muted-foreground">
                        <div className="col-span-2">Rating</div>
                        <div className="col-span-3">Candidate</div>
                        <div className="col-span-3">Position</div>
                        <div className="col-span-3">Feedback</div>
                        <div className="col-span-1 text-right">Date</div>
                    </div>
                    <div className="divide-y divide-border/50">
                        {feedbacks.map((fb) => (
                            <Tooltip key={fb.id}>
                                <TooltipTrigger asChild>
                                    <div className="grid grid-cols-12 gap-4 px-6 py-4 items-center hover:bg-muted/30 transition-colors group cursor-pointer relative">
                                        <div className="col-span-2 flex gap-0.5">
                                            {[1, 2, 3, 4, 5].map(star => (
                                                <Star key={star} className={`h-4 w-4 ${star <= fb.ui_ux_rating ? 'fill-amber-400 text-amber-400' : 'text-muted-foreground/40'}`} />
                                            ))}
                                        </div>
                                        <div className="col-span-3 min-w-0">
                                            <div className="font-bold text-base truncate">{fb.candidate_name}</div>
                                            <div className="text-sm text-muted-foreground truncate">{fb.candidate_email}</div>
                                        </div>
                                        <div className="col-span-3 text-sm font-semibold text-primary/80 truncate">
                                            {fb.job_title}
                                        </div>
                                        <div className="col-span-3">
                                            <p className="text-sm text-muted-foreground italic line-clamp-1">
                                                {fb.feedback_text ? `"${fb.feedback_text}"` : "No specific comments"}
                                            </p>
                                        </div>
                                        <div className="col-span-1 text-right text-xs font-medium text-muted-foreground">
                                            {fb.created_at ? new Date(fb.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'N/A'}
                                        </div>
                                    </div>
                                </TooltipTrigger>
                                <TooltipContent>
                                    Click to expand feedback
                                </TooltipContent>
                            </Tooltip>
                        ))}
                    </div>
                </div>
            ) : (
                <div className="bg-card rounded-2xl border border-border overflow-hidden shadow-sm">
                    {/* List Header */}
                    <div className="grid grid-cols-12 gap-4 px-4 py-3 bg-muted/50 border-b border-border text-xs uppercase tracking-widest font-black text-muted-foreground">
                        <div className="col-span-1 text-center">#</div>
                        <div className="col-span-2">Type</div>
                        <div className="col-span-3">Candidate</div>
                        <div className="col-span-3">Issue Description</div>
                        <div className="col-span-2 text-center">Status</div>
                        <div className="col-span-1 text-right">Date</div>
                    </div>
                    <div className="divide-y divide-border/50">
                        {tickets.map((ticket) => (
                            <div
                                key={ticket.id}
                                onClick={() => { setSelectedTicket(ticket); setHrResponse(ticket.hr_response || '') }}
                                className="grid grid-cols-12 gap-4 px-4 py-4 items-center hover:bg-muted/30 transition-all cursor-pointer group"
                            >
                                <div className="col-span-1 flex justify-center text-sm font-bold text-muted-foreground">
                                    {ticket.id}
                                </div>
                                <div className="col-span-2">
                                    <Badge variant="outline" className={`text-xs font-black uppercase px-2 py-0 border-none ${getIssueTypeBadge(ticket.issue_type)}`}>
                                        {ticket.issue_type.replace(/_/g, ' ')}
                                    </Badge>
                                </div>
                                <div className="col-span-3 min-w-0">
                                    <div className="font-bold text-base truncate">{ticket.candidate_name}</div>
                                    <div className="text-xs text-muted-foreground truncate">{ticket.candidate_email}</div>
                                </div>
                                <div className="col-span-3">
                                    <p className="text-sm text-muted-foreground line-clamp-2 pr-2">
                                        {ticket.description}
                                    </p>
                                </div>
                                <div className="col-span-2 flex justify-center">
                                    {ticket.status === 'pending' && (
                                        <Badge className="bg-amber-100 text-amber-700 border-amber-200 border font-bold text-xs">Pending</Badge>
                                    )}
                                    {ticket.status === 'resolved' && (
                                        <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 border font-bold text-xs">{ticket.is_reissue_granted ? '🔑 Re-issued' : '✓ Resolved'}</Badge>
                                    )}
                                    {ticket.status === 'dismissed' && (
                                        <Badge className="bg-slate-100 text-slate-500 border-slate-200 border font-bold text-xs">Dismissed</Badge>
                                    )}
                                </div>
                                <div className="col-span-1 text-right text-xs font-medium text-muted-foreground">
                                    {new Date(ticket.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {resp?.total > 0 && (
                <div className="sticky bottom-6 bg-background/80 backdrop-blur-xl border-t border-border p-4 -mx-6 z-30 shadow-[0_-4px_12px_-4px_rgba(0,0,0,0.1)] mt-8">
                    <div className="flex flex-col sm:flex-row items-center justify-between gap-4 max-w-[1600px] mx-auto px-6">
                        <div className="text-sm font-bold text-muted-foreground uppercase tracking-widest">
                            Showing {((currentPage - 1) * pageSize) + 1} - {Math.min(currentPage * pageSize, resp.total)} of {resp.total}
                        </div>
                        <div className="flex items-center gap-3">
                            <Button
                                variant="outline"
                                size="lg"
                                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                                disabled={currentPage === 1 || isLoading}
                                className="h-11 px-6 rounded-xl font-bold bg-background dark:bg-muted hover:bg-accent border-border transition-all shadow-sm active:scale-95 disabled:opacity-50"
                            >
                                <ChevronLeft className="mr-2 h-5 w-5" /> Previous
                            </Button>
                            <div className="px-4 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg text-sm font-bold text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                                Page {currentPage} of {Math.ceil(resp.total / pageSize)}
                            </div>
                            <Button
                                variant="outline"
                                size="lg"
                                onClick={() => setCurrentPage(prev => prev + 1)}
                                disabled={currentPage >= Math.ceil(resp.total / pageSize) || isLoading}
                                className="h-11 px-6 rounded-xl font-bold bg-background dark:bg-muted hover:bg-accent border-border transition-all shadow-sm active:scale-95 disabled:opacity-50"
                            >
                                Next <ChevronRight className="ml-2 h-5 w-5" />
                            </Button>
                        </div>

                        <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-muted-foreground">Show</span>
                            <Select
                                value={String(pageSize)}
                                onValueChange={(val) => {
                                    setPageSize(Number(val));
                                    setCurrentPage(1);
                                }}
                            >
                                <SelectTrigger className="h-10 w-[85px] rounded-xl border-border bg-background font-bold shadow-none focus:ring-0">
                                    <SelectValue placeholder="10" />
                                </SelectTrigger>
                                <SelectContent className="min-w-[70px]">
                                    {[5, 10, 20, 50, 100].map((size) => (
                                        <SelectItem key={size} value={String(size)} className="font-bold">
                                            {size}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <span className="text-sm font-bold text-muted-foreground">per page</span>
                        </div>
                    </div>
                </div>
            )}

            {/* Resolution Dialog */}
            <Dialog open={!!selectedTicket} onOpenChange={(open) => !open && setSelectedTicket(null)}>
                <DialogContent className="max-w-5xl w-[95vw] sm:w-[90vw] bg-card border-border shadow-2xl p-0 overflow-hidden">
                    <DialogHeader className="p-6 pb-0">
                        <DialogTitle className="text-2xl font-black tracking-tight flex items-center gap-2">
                            Ticket Details
                            {selectedTicket && (
                                <Badge variant="outline" className={`capitalize ${getIssueTypeBadge(selectedTicket.issue_type)}`}>
                                    {selectedTicket.issue_type.replace('_', ' ')}
                                </Badge>
                            )}
                        </DialogTitle>
                        <DialogDescription>
                            Review the candidate's reported issue and take necessary action.
                        </DialogDescription>
                    </DialogHeader>

                    {selectedTicket && (
                        <>
                            <div className="space-y-6 px-6 py-4 max-h-[70vh] overflow-y-auto min-w-0">
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 bg-muted/50 p-6 rounded-2xl border border-border/50">
                                    {/* LEFT: Candidate Info */}
                                    <div className="space-y-2 min-w-0">
                                        <Label className="text-xs uppercase tracking-widest text-muted-foreground font-black">Candidate</Label>
                                        <div className="flex items-center gap-2 font-bold text-xl truncate">
                                            <User className="h-6 w-6 text-primary flex-shrink-0" />
                                            <span className="truncate">{selectedTicket.candidate_name}</span>
                                        </div>
                                        <div className="flex items-center gap-1.5 text-sm text-muted-foreground truncate">
                                            <Mail className="h-4 w-4 flex-shrink-0" />
                                            <span className="truncate">{selectedTicket.candidate_email}</span>
                                        </div>
                                        {selectedTicket.test_id && (
                                            <Badge variant="secondary" className="text-xs font-bold w-fit">
                                                Interview ID: {selectedTicket.test_id}
                                            </Badge>
                                        )}
                                    </div>
                                    {/* RIGHT: Job / Application Links */}
                                    <div className="space-y-2 min-w-0">
                                        <Label className="text-xs uppercase tracking-widest text-muted-foreground font-black">Job Position</Label>
                                        {selectedTicket.job_identifier ? (
                                            <Badge variant="outline" className="border-primary/30 text-primary font-black px-3 py-1 w-fit text-sm">
                                                {selectedTicket.job_identifier}
                                            </Badge>
                                        ) : (
                                            <Badge variant="outline" className="border-muted text-muted-foreground font-black px-3 py-1 w-fit text-sm">Unknown Job</Badge>
                                        )}
                                        {selectedTicket.application_id && (
                                            <div>
                                                <Link
                                                    href={`/dashboard/hr/applications/${selectedTicket.application_id}`}
                                                    onClick={() => setSelectedTicket(null)}
                                                    className="text-xs text-primary underline underline-offset-2 font-semibold hover:opacity-70 transition-opacity"
                                                >
                                                    View Candidate Application →
                                                </Link>
                                            </div>
                                        )}
                                        <div className="flex items-center gap-1.5 text-sm text-muted-foreground font-medium">
                                            <Clock className="h-4 w-4 text-primary/70 flex-shrink-0" />
                                            {new Date(selectedTicket.created_at).toLocaleString()}
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-3 min-w-0">
                                    <Label className="text-xs uppercase tracking-widest text-muted-foreground font-black flex items-center gap-2">
                                        <AlertCircle className="h-4 w-4 text-destructive" />
                                        Issue Description
                                    </Label>
                                    <div className="p-6 bg-card rounded-2xl border-2 border-border/50 text-foreground font-medium text-base leading-relaxed shadow-sm max-w-full overflow-hidden break-words">
                                        {selectedTicket.description}
                                    </div>
                                </div>

                                {selectedTicket.status === 'pending' ? (
                                    <div className="space-y-4 min-w-0">
                                        <Separator />
                                        <div className="space-y-2">
                                            <Label className="text-base font-bold flex items-center gap-2">
                                                <MessageSquare className="h-5 w-5 text-primary" />
                                                Your Response
                                            </Label>
                                            <Textarea
                                                placeholder="Explain the resolution or why the appeal was rejected..."
                                                className="min-h-[140px] rounded-xl border-2 focus:ring-primary/20 transition-all font-medium w-full text-base"
                                                value={hrResponse}
                                                onChange={(e) => setHrResponse(e.target.value)}
                                            />
                                            <p className="text-xs text-muted-foreground">This response will be sent to the candidate's email.</p>
                                        </div>

                                        <div className="flex items-center space-x-2 bg-primary/5 p-3 rounded-xl border border-primary/10">
                                            <Switch
                                                id="send-email"
                                                checked={sendEmail}
                                                onCheckedChange={setSendEmail}
                                            />
                                            <Label htmlFor="send-email" className="text-sm font-bold text-primary cursor-pointer leading-none">
                                                Send email notification to candidate
                                            </Label>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="space-y-4 min-w-0">
                                        <Separator />
                                        <div className="space-y-2">
                                            <Label className="text-xs uppercase tracking-widest text-muted-foreground font-black">HR Response</Label>
                                            <div className="p-5 bg-primary/5 rounded-xl border border-primary/20 text-primary text-base font-medium break-words">
                                                {selectedTicket.hr_response}
                                            </div>
                                            <div className="flex flex-wrap justify-between items-center gap-2 mt-2">
                                                <span className="text-sm text-muted-foreground flex items-center gap-1.5">
                                                    <CheckCircle2 className="h-4 w-4 text-green-500" />
                                                    Resolved {selectedTicket.resolved_at ? new Date(selectedTicket.resolved_at).toLocaleDateString() : ''}
                                                </span>
                                                {selectedTicket.is_reissue_granted && (
                                                    <Badge className="bg-primary text-primary-foreground font-bold px-3 py-1">Key Re-issued</Badge>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                            <DialogFooter className="p-4 sm:p-6 border-t bg-muted/20">
                                {selectedTicket.status === 'pending' ? (
                                    <div className="flex flex-wrap gap-2 w-full">
                                        <Button
                                            variant="ghost"
                                            className="flex-1 min-w-[120px] font-semibold text-muted-foreground hover:text-destructive hover:bg-destructive/5 rounded-xl h-12 px-3 transition-all"
                                            onClick={() => handleResolve(selectedTicket.id, 'dismissed')}
                                            disabled={isResolving}
                                        >
                                            <XCircle className="h-4 w-4 mr-2" />
                                            Dismiss
                                        </Button>

                                        <Button
                                            variant="outline"
                                            className="flex-1 min-w-[120px] font-bold border-2 border-primary/10 hover:border-primary/40 hover:bg-primary/5 text-primary rounded-xl h-12 px-3 transition-all active:scale-95"
                                            onClick={() => handleResolve(selectedTicket.id, 'reply')}
                                            disabled={isResolving || !hrResponse.trim()}
                                        >
                                            <Send className="h-4 w-4 mr-2" />
                                            Reply
                                        </Button>

                                        <Button
                                            variant="outline"
                                            className="flex-1 min-w-[120px] font-bold border-2 border-primary/20 hover:border-primary text-primary rounded-xl h-12 px-3 transition-all active:scale-95"
                                            onClick={() => handleResolve(selectedTicket.id, 'resolve')}
                                            disabled={isResolving}
                                        >
                                            <CheckCircle2 className="h-4 w-4 mr-2" />
                                            Resolve
                                        </Button>

                                        {selectedTicket.interview_id && (
                                            <Button
                                                className="flex-[2] min-w-[180px] font-bold bg-primary hover:bg-primary/90 text-white shadow-md rounded-xl h-12 px-4 transition-all active:scale-95 animate-in fade-in slide-in-from-right-2 duration-500"
                                                onClick={() => handleResolve(selectedTicket.id, 'reissue_key')}
                                                disabled={isResolving}
                                            >
                                                <RotateCcw className="h-4 w-4 mr-2" />
                                                Re-issue & Resolve
                                            </Button>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-between w-full gap-4">
                                        <div className="text-sm text-muted-foreground">
                                            {selectedTicket.status === 'resolved' ? '✅ This ticket has been resolved.' : '🚫 This ticket was dismissed.'}
                                            {selectedTicket.resolved_at && (
                                                <span className="ml-1">({new Date(selectedTicket.resolved_at).toLocaleDateString()})</span>
                                            )}
                                        </div>
                                        <Button onClick={() => setSelectedTicket(null)} className="font-bold h-12 rounded-xl px-8">Close</Button>
                                    </div>
                                )}
                            </DialogFooter>
                        </>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    )
}
