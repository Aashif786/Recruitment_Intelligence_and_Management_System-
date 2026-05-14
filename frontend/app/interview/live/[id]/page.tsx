'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import InterviewSession from '@/modules/interview/InterviewSession';

export default function LiveInterviewPage() {
    const params = useParams();
    const searchParams = useSearchParams();
    const [token, setToken] = useState('');

    const sessionId = (params.id as string) || 'test-session';

    useEffect(() => {
        const q = searchParams.get('token');
        const fromStorage = typeof window !== 'undefined' ? localStorage.getItem('interview_token') : null;
        setToken(q?.trim() || fromStorage?.trim() || '');
    }, [searchParams]);

    return (
        <div className="min-h-screen bg-[#f8fafc] flex flex-col pt-12">
            <header className="fixed top-0 w-full h-16 bg-white/80 backdrop-blur-md border-b border-slate-200 px-10 flex items-center justify-between z-20">
                <div className="flex items-center gap-6">
                    <h1 className="text-xl font-black text-slate-900 tracking-tight">Enterprise WebSockets Interview</h1>
                </div>
                <div className="text-sm font-medium text-slate-500">
                    Session: {sessionId}
                </div>
            </header>

            <main className="flex-1 w-full max-w-7xl mx-auto p-6 md:p-12 overflow-hidden">
                {token ? (
                    <InterviewSession sessionId={sessionId} token={token} />
                ) : (
                    <p className="text-center text-muted-foreground mt-12">
                        Missing interview token. Open this page from your interview link, complete access on{' '}
                        <a href="/interview/access" className="text-primary underline">/interview/access</a>
                        , or add <code className="text-xs">?token=…</code> for testing.
                    </p>
                )}
            </main>
        </div>
    );
}
