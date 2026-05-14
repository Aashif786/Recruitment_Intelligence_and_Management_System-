'use client'

import React, { useState, useEffect, Suspense, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { API_BASE_URL } from '@/lib/config'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

function InterviewAccessForm() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [accessKey, setAccessKey] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  /**
   * Holds the pending auto-submit `setTimeout` id (cleared on unmount / before reschedule).
   * Named per interview access spec; value is a timer handle or null, not a boolean.
   */
  const autoAccessStartedRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hasAttemptedRef = useRef<string | null>(null)
  const isSubmittingRef = useRef(false)

  const handleSubmit = async (emailVal?: string, keyVal?: string) => {
    const finalEmail = emailVal ?? email
    const finalKey = keyVal ?? accessKey
    if (!finalEmail || !finalKey) return
    if (loading || isSubmittingRef.current) return
    
    isSubmittingRef.current = true
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE_URL}/api/interviews/access`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: finalEmail, access_key: finalKey })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Access failed')
      // Store interview JWT separately to avoid clobbering global HR/admin auth.
      localStorage.setItem('interview_token', data.access_token)
      router.push('/interview/' + data.interview_id)
    } catch (err: any) {
      setError(err.message)
      isSubmittingRef.current = false
    } finally {
      setLoading(false)
    }
  }

  const e = searchParams.get('email')
  const k = searchParams.get('key')

  useEffect(() => {
    if (e) setEmail(e)
    if (k) setAccessKey(k)
  }, [e, k])

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
        <Card className="max-w-md w-full shadow-lg border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-2xl">
            <CardHeader className="text-center">
                <CardTitle className="text-2xl font-bold text-slate-800 dark:text-slate-200">Interview Access</CardTitle>
                <CardDescription>Enter your email and access key to begin.</CardDescription>
            </CardHeader>
            <CardContent>
                <form onSubmit={(e) => { e.preventDefault(); handleSubmit(); }} className="space-y-4">
                    {error && <p className="text-red-500 text-sm text-center">{error}</p>}
                    <div className="space-y-1">
                        <Label htmlFor="email">Email</Label>
                        <Input
                            id="email"
                            type="email"
                            placeholder="you@example.com"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            disabled={loading}
                        />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="key">Access Key</Label>
                        <Input
                            id="key"
                            type="text"
                            placeholder="Your access key"
                            value={accessKey}
                            onChange={(e) => setAccessKey(e.target.value.trim())}
                            required
                            disabled={loading}
                        />
                    </div>
                    <Button type="submit" className="w-full" disabled={loading || !email || !accessKey}>
                        {loading ? 'Verifying...' : 'Enter Interview'}
                    </Button>
                </form>
            </CardContent>
        </Card>
    </div>
  )
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <InterviewAccessForm />
    </Suspense>
  )
}
