'use client'

import React, { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Calendar } from 'lucide-react'
import { APIClient } from '@/app/dashboard/lib/api-client'
import { toast } from "sonner"

export function SendOfferDialog({ applicationId, candidateName, onSuccess, trigger }: { applicationId: number, candidateName: string, onSuccess: () => void, trigger: React.ReactNode }) {
    const [open, setOpen] = useState(false)
    const [loading, setLoading] = useState(false)
    const [joiningDate, setJoiningDate] = useState('')

    const handleSend = async () => {
        if (!joiningDate) {
            toast.error("Please select a joining date")
            return
        }

        setLoading(true)
        try {
            // Always auto_approve for job owners as requested
            const url = `/api/onboarding/applications/${applicationId}/send-offer?joining_date=${joiningDate}&auto_approve=true`
            await APIClient.post(url, {})
            toast.success(`Offer letter has been sent directly to ${candidateName}.`)
            setOpen(false)
            onSuccess()
        } catch (error: any) {
            toast.error(error.message || "Could not process offer")
        } finally {
            setLoading(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                {trigger}
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle className="text-xl font-black">Issue Offer Letter</DialogTitle>
                    <DialogDescription>
                        Set the joining date and release the offer letter to <strong>{candidateName}</strong> immediately.
                    </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                    <div className="space-y-2">
                        <Label htmlFor="joining_date" className="font-bold">Joining Date</Label>
                        <div className="relative">
                            <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-primary" />
                            <Input 
                                id="joining_date" 
                                type="date" 
                                min={new Date().toISOString().split('T')[0]}
                                className="pl-10 h-10 border-primary/20 focus-visible:ring-primary"
                                value={joiningDate}
                                onChange={(e) => setJoiningDate(e.target.value)}
                            />
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={() => setOpen(false)} disabled={loading}>
                        Cancel
                    </Button>
                    <Button 
                        onClick={handleSend} 
                        disabled={loading} 
                        className="font-black bg-primary hover:bg-primary/90 px-8"
                    >
                        {loading ? "Releasing..." : "Release Offer"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
