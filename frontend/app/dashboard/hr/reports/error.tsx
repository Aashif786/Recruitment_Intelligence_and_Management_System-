'use client'

import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { AlertCircle } from 'lucide-react'

export default function ErrorBoundary({
    error,
    reset,
}: {
    error: Error & { digest?: string }
    reset: () => void
}) {
    useEffect(() => {
        console.error('Reports Error:', error)
    }, [error])

    return (
        <div className="h-full flex flex-col items-center justify-center p-8 text-center animate-in fade-in duration-500">
            <div className="w-16 h-16 bg-destructive/10 text-destructive rounded-full flex items-center justify-center mb-6">
                <AlertCircle className="w-8 h-8" />
            </div>
            <h2 className="text-2xl font-bold mb-3 tracking-tight">Report rendering failed</h2>
            <p className="text-muted-foreground max-w-md mx-auto mb-8">
                An unexpected error occurred while generating this report view.
            </p>
            <div className="flex gap-4 justify-center">
                <Button onClick={() => reset()} variant="default">
                    Try again
                </Button>
            </div>
        </div>
    )
}
