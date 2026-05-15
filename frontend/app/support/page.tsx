'use client'

import React, { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { APIClient } from '@/app/dashboard/lib/api-client'
import { toast } from "sonner"
import { AlertTriangle, Send, CheckCircle2, ChevronLeft, ShieldCheck, Loader2 } from 'lucide-react'
import { useRouter, useSearchParams } from 'next/navigation'

export default function SupportPage() {
    const router = useRouter()
    const searchParams = useSearchParams()
    const [email, setEmail] = useState('')
    const [accessKey, setAccessKey] = useState('')
    const [issueType, setIssueType] = useState('technical')
    const [description, setDescription] = useState('')
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [isSubmitted, setIsSubmitted] = useState(false)
    const [formError, setFormError] = useState('')

    const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
    const descriptionTrimmed = description.trim()
    const descriptionValid = descriptionTrimmed.length >= 10 && descriptionTrimmed.length <= 5000
    const canSubmit = Boolean(email.trim() && accessKey.trim() && emailValid && descriptionValid && !isSubmitting)

    useEffect(() => {
        const e = searchParams.get('email')
        const k = searchParams.get('access_key')
        if (e) setEmail(e)
        if (k) setAccessKey(k)
    }, [searchParams])

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (isSubmitting) return
        setFormError('')

        if (!email.trim() || !accessKey.trim() || !descriptionTrimmed) {
            const msg = "Please fill in all fields"
            setFormError(msg)
            toast.error(msg)
            return
        }
        if (!emailValid) {
            const msg = "Please enter a valid email address."
            setFormError(msg)
            toast.error(msg)
            return
        }
        if (!descriptionValid) {
            const msg = "Description must be between 10 and 5000 characters."
            setFormError(msg)
            toast.error(msg)
            return
        }

        try {
            setIsSubmitting(true)
            await APIClient.post('/api/support/ticket', {
                email,
                access_key: accessKey,
                grievance_type: issueType,
                description: descriptionTrimmed,
            })
            setIsSubmitted(true)
            toast.success("Your support request has been recorded and sent to HR.")
        } catch (err: any) {
            console.error("Failed to report grievance:", err)
            const msg = err.message || "Failed to submit report. Ensure your email and access key are correct."
            setFormError(msg)
            toast.error(msg)
        } finally {
            setIsSubmitting(false)
        }
    }

    if (isSubmitted) {
        return (
            <div className="flex-1 min-h-screen flex items-center justify-center bg-muted/30 p-6 relative overflow-hidden">
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-3xl h-96 bg-blue-500/10 blur-[120px] pointer-events-none" />
                
                <Card className="max-w-md w-full border border-border/50 shadow-[0_32px_64px_-12px_rgba(0,0,0,0.1)] bg-card/80 backdrop-blur-xl rounded-[3rem] overflow-hidden animate-in zoom-in-95 fade-in duration-700">
                    <div className="h-2 bg-green-500"></div>
                    <CardHeader className="text-center p-12 pb-6">
                        <div className="mx-auto w-24 h-24 bg-green-50 rounded-3xl flex items-center justify-center text-green-600 mb-8 border border-green-100 shadow-xl shadow-green-500/10 rotate-3 transition-transform hover:rotate-0">
                            <CheckCircle2 className="h-12 w-12" />
                        </div>
                        <CardTitle className="text-3xl font-black tracking-tight text-slate-900 uppercase">Grievance Recorded</CardTitle>
                        <CardDescription className="text-lg font-bold text-slate-500 mt-4 leading-relaxed">
                            Thank you for your patience. Your report has been securely transmitted to our HR Integrity Team.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="text-center px-12 pb-8">
                        <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100 text-sm font-bold text-slate-600">
                            A confirmation and resolution will be sent to <span className="text-blue-600">{email}</span> shortly.
                        </div>
                    </CardContent>
                    <CardFooter className="flex flex-col gap-3 p-12 pt-0">
                        <Button 
                            onClick={() => router.push('/')} 
                            className="w-full h-14 rounded-2xl bg-slate-900 hover:bg-slate-800 text-white font-black text-lg shadow-xl"
                        >
                            RETURN TO PORTAL
                        </Button>
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-4">
                            ID: {Math.random().toString(36).substring(7).toUpperCase()}
                        </p>
                    </CardFooter>
                </Card>
            </div>
        )
    }

    return (
        <div className="flex-1 min-h-full bg-muted/30 flex flex-col items-center justify-start p-4 py-12 md:py-20 relative overflow-y-auto">
            {/* Background decorative elements */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-4xl h-96 bg-gradient-to-b from-blue-500/5 to-transparent blur-3xl pointer-events-none" />

            <div className="w-full max-w-2xl relative z-10">
                <Button
                    variant="ghost"
                    onClick={() => router.back()}
                    className="mb-8 hover:bg-background/80 text-muted-foreground group font-bold rounded-xl px-4"
                >
                    <ChevronLeft className="mr-2 h-4 w-4 transition-transform group-hover:-translate-x-1" /> 
                    Back to Interview
                </Button>

                <Card className="border border-border/50 shadow-2xl bg-card/80 backdrop-blur-sm overflow-hidden rounded-[2.5rem] animate-in slide-in-from-bottom-8 duration-700 ease-out">
                    <div className="h-2 bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-600 animate-gradient-x"></div>
                    
                    <CardHeader className="space-y-4 p-8 md:p-12 pb-6">
                        <div className="flex items-center gap-6">
                            <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center text-white shadow-xl shadow-blue-500/20 rotate-3 transform-gpu transition-transform hover:rotate-0">
                                <AlertTriangle className="h-8 w-8" />
                            </div>
                            <div>
                                <CardTitle className="text-3xl md:text-4xl font-black tracking-tight text-slate-900 dark:text-white uppercase">Support Portal</CardTitle>
                                <CardDescription className="text-base md:text-lg font-bold text-slate-500 mt-1">
                                    Technical Grievance & Reschedule Requests
                                </CardDescription>
                            </div>
                        </div>
                    </CardHeader>

                    <CardContent className="p-8 md:p-12 pt-4">
                        <form onSubmit={handleSubmit} className="space-y-8">
                            {formError && (
                                <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-bold text-red-700 flex items-center gap-3 animate-shake" role="alert">
                                    <AlertTriangle className="h-5 w-5 shrink-0" />
                                    {formError}
                                </div>
                            )}

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div className="space-y-3">
                                    <Label htmlFor="email" className="text-xs font-black uppercase tracking-widest text-slate-400">
                                        Registered Email
                                    </Label>
                                    <Input
                                        id="email"
                                        type="email"
                                        placeholder="you@example.com"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className="h-14 px-5 rounded-2xl border-2 border-slate-100 focus:border-blue-600 focus:ring-0 text-lg transition-all font-bold"
                                        required
                                    />
                                </div>

                                <div className="space-y-3">
                                    <Label htmlFor="accessKey" className="text-xs font-black uppercase tracking-widest text-slate-400">
                                        Access Key
                                    </Label>
                                    <Input
                                        id="accessKey"
                                        type="text"
                                        placeholder="H4IE-..."
                                        value={accessKey}
                                        onChange={(e) => setAccessKey(e.target.value.trim())}
                                        className="h-14 px-5 rounded-2xl border-2 border-slate-100 focus:border-blue-600 focus:ring-0 tracking-widest font-mono text-lg transition-all"
                                        required
                                    />
                                </div>
                            </div>

                            <div className="space-y-4">
                                <Label className="text-xs font-black uppercase tracking-widest text-slate-400">Nature of Grievance</Label>
                                <RadioGroup value={issueType} onValueChange={setIssueType} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {[
                                        { id: 'technical', label: 'Technical Glitch', desc: 'Audio, Video, or UI issues' },
                                        { id: 'interruption', label: 'Session Interrupted', desc: 'Browser crash or exit' },
                                        { id: 'misconduct', label: 'Misconduct Appeal', desc: 'Appeal a proctoring warning' },
                                        { id: 'other', label: 'Other Issue', desc: 'Process or scheduling' }
                                    ].map((opt) => (
                                        <label key={opt.id} htmlFor={opt.id} className={`relative flex flex-col p-5 rounded-2xl border-2 transition-all cursor-pointer group ${issueType === opt.id
                                            ? 'border-blue-600 bg-blue-50/30'
                                            : 'border-slate-100 hover:border-blue-200 hover:bg-slate-50/50'
                                            }`}>
                                            <div className="flex items-center justify-between mb-1">
                                                <span className="font-black text-slate-900 dark:text-white">{opt.label}</span>
                                                <RadioGroupItem value={opt.id} id={opt.id} className="sr-only" />
                                                <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${issueType === opt.id ? 'border-blue-600 bg-blue-600' : 'border-slate-300'}`}>
                                                    {issueType === opt.id && <div className="w-2 h-2 rounded-full bg-white" />}
                                                </div>
                                            </div>
                                            <span className="text-xs text-slate-500 font-bold">{opt.desc}</span>
                                        </label>
                                    ))}
                                </RadioGroup>
                            </div>

                            <div className="space-y-3">
                                <Label htmlFor="description" className="text-xs font-black uppercase tracking-widest text-slate-400">Detailed Description</Label>
                                <Textarea
                                    id="description"
                                    placeholder="Please describe exactly what happened..."
                                    className="min-h-[160px] p-6 rounded-2xl border-2 border-slate-100 focus:border-blue-600 focus:ring-0 text-lg transition-all resize-none font-medium"
                                    value={description}
                                    onChange={(e) => setDescription(e.target.value)}
                                    required
                                />
                                <div className="flex items-center gap-2 text-[10px] text-slate-400 font-black uppercase tracking-tighter italic">
                                    <ShieldCheck className="h-3 w-3" />
                                    Your IP and session data will be correlated for verification
                                </div>
                            </div>

                            <Button
                                type="submit"
                                className="w-full h-18 rounded-2xl bg-slate-900 hover:bg-slate-800 text-white font-black text-xl shadow-2xl transition-all active:scale-[0.98] disabled:opacity-50"
                                disabled={!canSubmit}
                            >
                                {isSubmitting ? (
                                    <div className="flex items-center gap-3">
                                        <Loader2 className="h-6 w-6 animate-spin" />
                                        RECORDING REPORT...
                                    </div>
                                ) : (
                                    <div className="flex items-center gap-3">
                                        SUBMIT GRIEVANCE <Send className="h-6 w-6" />
                                    </div>
                                )}
                            </Button>
                        </form>
                    </CardContent>
                </Card>

                <div className="mt-12 text-center pb-8 animate-in fade-in duration-1000 delay-500">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">
                        CAL-RIMS AI Recruitment Platform • Secure Support
                    </p>
                </div>
            </div>
        </div>
    )
}
