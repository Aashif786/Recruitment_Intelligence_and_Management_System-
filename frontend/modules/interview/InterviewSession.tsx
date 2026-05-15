'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import QuestionPanel from './QuestionPanel';
import AnswerInput from './AnswerInput';
import ScoreIndicator from './ScoreIndicator';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { API_BASE_URL } from '@/lib/config';
import { toast } from 'sonner';
import { APIClient } from '@/app/dashboard/lib/api-client';

import * as tf from '@tensorflow/tfjs-core';
import '@tensorflow/tfjs-backend-webgl';
import * as blazeface from '@tensorflow-models/blazeface';
import {
  Loader2, ShieldCheck, ShieldAlert,
  UserCheck, Eye, BrainCircuit
} from 'lucide-react';
import InterviewSidebar from './InterviewSidebar';

interface InterviewSessionProps {
  sessionId: string;
  token: string;
}

// ─── helpers ──────────────────────────────────────────────────────────────────
function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

async function apiFetch(path: string, token: string, opts: RequestInit = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...opts,
    headers: { ...authHeaders(token), ...(opts.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

// ─── component ────────────────────────────────────────────────────────────────
export default function InterviewSession({ sessionId, token }: InterviewSessionProps) {
  const interviewId = sessionId;

  // ── session state ──
  const [isReady, setIsReady] = useState(false);       // questions loaded
  const [isLoading, setIsLoading] = useState(true);    // first load spinner
  const [isFinished, setIsFinished] = useState(false);
  const [isTerminated, setIsTerminated] = useState(false);
  const [focusStrikes, setFocusStrikes] = useState(0);
  const sessionStartRef = useRef(Date.now());

  // ── question state ──
  const [totalQuestions, setTotalQuestions] = useState(20);
  const [currentQuestionNumber, setCurrentQuestionNumber] = useState(1);
  const [currentQuestion, setCurrentQuestion] = useState<{
    id: number;
    question: string;
    difficulty: string;
    options?: string[];
    answer_text?: string | null;
    question_type?: string;
  } | null>(null);
  const [completedQuestions, setCompletedQuestions] = useState<number[]>([]);
  const [incorrectQuestions, setIncorrectQuestions] = useState<number[]>([]);
  const [latestFeedback, setLatestFeedback] = useState<{ score: number; text: string } | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [messages, setMessages] = useState<string[]>([]);
  const addMsg = (m: string) => setMessages(prev => [...prev, m]);

  // ── proctoring ──
  const [isFaceDetected, setIsFaceDetected] = useState(true);
  const [isFocusingOnMonitor, setIsFocusingOnMonitor] = useState(true);
  const detectorRef = useRef<any>(null);
  const faceCheckIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const sessionVideoRef = useRef<HTMLVideoElement>(null);

  // ── audio ──
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const transcriptionCallbackRef = useRef<((text: string) => void) | null>(null);

  // ── video recording ──
  const videoRecorderRef = useRef<MediaRecorder | null>(null);
  const videoChunksRef = useRef<Blob[]>([]);

  // ─── SECURITY VIOLATION ────────────────────────────────────────────────────
  const terminationSentRef = useRef(false);

  const handleStrike = useCallback((reason: string) => {
    if (Date.now() - sessionStartRef.current < 15000) return; // ignore first 15s

    setFocusStrikes(prev => {
      const next = prev + 1;
      if (next < 4) {
        toast.error(`Warning ${next}/4: ${reason}`, {
          description: 'Multiple violations will result in immediate session termination.',
          duration: 5000,
        });
      } else {
        if (!terminationSentRef.current) {
          terminationSentRef.current = true;
          setIsTerminated(true);
          fetch(`${API_BASE_URL}/api/interviews/${interviewId}/security-violation`, {
            method: 'POST',
            headers: authHeaders(token),
            body: JSON.stringify({ reason }),
          }).catch(console.error);
        }
      }
      return next;
    });
  }, [interviewId, token]);

  // ─── VIDEO UPLOAD ──────────────────────────────────────────────────────────
  const uploadVideo = useCallback(async (blob: Blob) => {
    if (blob.size < 1000) return;
    try {
      const formData = new FormData();
      formData.append('file', blob, 'interview_session.webm');
      await APIClient.postMultipart(`/api/interviews/${interviewId}/upload-video`, formData, `v-${Date.now()}`);
    } catch (err) {
      console.error('Video upload failed:', err);
    }
  }, [interviewId]);

  // ─── LOAD QUESTIONS (poll until ready) ────────────────────────────────────
  const loadCurrentQuestion = useCallback(async (questionNumber?: number) => {
    try {
      if (questionNumber !== undefined) {
        // Jump to specific question
        const all: any[] = await apiFetch(`/api/interviews/${interviewId}/questions`, token);
        const q = all.find((x: any) => x.question_number === questionNumber);
        if (q) {
          setCurrentQuestion({
            id: q.id,
            question: q.question_text,
            difficulty: 'medium',
            options: q.question_options ? JSON.parse(q.question_options) : undefined,
            answer_text: q.answer_text,
            question_type: q.question_type,
          });
          setCurrentQuestionNumber(q.question_number);
          const answered = all.filter((x: any) => x.is_answered).map((x: any) => x.question_number);
          const incorrect = all.filter((x: any) => x.is_answered && x.answer_score !== null && x.answer_score < 5).map((x: any) => x.question_number);
          setCompletedQuestions(answered);
          setIncorrectQuestions(incorrect);
          setTotalQuestions(all.length);
        }
      } else {
        // Get current unanswered question
        const res = await apiFetch(`/api/interviews/${interviewId}/current-question`, token);
        if (res.status === 'processing' || !res.id) return;
        setCurrentQuestion({
          id: res.id,
          question: res.question_text,
          difficulty: 'medium',
          options: res.question_options ? JSON.parse(res.question_options) : undefined,
          answer_text: null,
          question_type: res.question_type,
        });
        setCurrentQuestionNumber(res.question_number);
      }
    } catch (err: any) {
      if (err.message?.includes('410') || err.message?.toLowerCase().includes('complet')) {
        setIsFinished(true);
      }
    }
  }, [interviewId, token]);

  // Handle video recording stop and upload when finished
  useEffect(() => {
    if (isFinished && videoRecorderRef.current && videoRecorderRef.current.state !== 'inactive') {
      videoRecorderRef.current.stop();
    }
  }, [isFinished]);

  // Initial poll: wait for questions to be ready
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const stage = await apiFetch(`/api/interviews/${interviewId}/stage`, token);
        if (stage.status === 'processing' || !stage.questions_ready) {
          if (!cancelled) setTimeout(poll, 2500);
          return;
        }
        if (stage.status === 'completed' || stage.interview_stage === 'completed') {
          setIsFinished(true);
          setIsLoading(false);
          return;
        }
        // Load all questions to populate sidebar
        const all: any[] = await apiFetch(`/api/interviews/${interviewId}/questions`, token);
        if (!cancelled) {
          setTotalQuestions(all.length || stage.total_questions || 20);
          const answered = all.filter((x: any) => x.is_answered).map((x: any) => x.question_number);
          const incorrect = all.filter((x: any) => x.is_answered && x.answer_score !== null && x.answer_score < 5).map((x: any) => x.question_number);
          setCompletedQuestions(answered);
          setIncorrectQuestions(incorrect);
          await loadCurrentQuestion();
          setIsReady(true);
          setIsLoading(false);
        }
      } catch (e: any) {
        if (!cancelled) setTimeout(poll, 3000);
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [interviewId, token, loadCurrentQuestion]);

  // ─── SUBMIT ANSWER ─────────────────────────────────────────────────────────
  const handleSubmitAnswer = async (text: string) => {
    if (!text.trim() || !currentQuestion) return;
    setIsEvaluating(true);
    setLatestFeedback(null);
    addMsg('Analyzing your response...');
    try {
      const res = await apiFetch(`/api/interviews/${interviewId}/submit-answer`, token, {
        method: 'POST',
        body: JSON.stringify({ question_id: currentQuestion.id, answer_text: text }),
      });

      if (res.terminated) {
        setIsTerminated(true);
        return;
      }

      setCompletedQuestions(prev => [...new Set([...prev, currentQuestionNumber])]);
      addMsg('Response recorded. Loading next question...');

      // Poll for evaluation result (non-blocking — show next question immediately)
      const nextNum = currentQuestionNumber + 1;
      await loadCurrentQuestion(nextNum).catch(() => setIsFinished(true));

      // Background: poll for score after short delay
      setTimeout(async () => {
        try {
          const all: any[] = await apiFetch(`/api/interviews/${interviewId}/questions`, token);
          const answered = all.find((q: any) => q.question_number === currentQuestionNumber);
          if (answered?.answer_score !== null && answered?.answer_score !== undefined) {
            setLatestFeedback({ score: answered.answer_score, text: '' });
            if (answered.answer_score < 5) {
              setIncorrectQuestions(prev => [...new Set([...prev, currentQuestionNumber])]);
            }
          }
        } catch { /* ignore */ }
      }, 4000);

    } catch (err: any) {
      if (err.message?.includes('410') || err.message?.toLowerCase().includes('complet')) {
        setIsFinished(true);
      } else {
        toast.error('Failed to submit answer. Please try again.');
      }
    } finally {
      setIsEvaluating(false);
    }
  };

  // ─── NAVIGATION ───────────────────────────────────────────────────────────
  const jumpToQuestion = useCallback(async (num: number) => {
    if (num < 1 || num > totalQuestions) return;
    if (isEvaluating) { toast.warning('Please wait for evaluation to complete.'); return; }
    setIsLoading(true);
    await loadCurrentQuestion(num);
    setIsLoading(false);
  }, [totalQuestions, isEvaluating, loadCurrentQuestion]);

  const handleNext = () => currentQuestionNumber < totalQuestions && jumpToQuestion(currentQuestionNumber + 1);
  const handlePrev = () => currentQuestionNumber > 1 && jumpToQuestion(currentQuestionNumber - 1);

  // ─── TRANSCRIPTION ─────────────────────────────────────────────────────────
  const startRecording = (callback?: (text: string) => void) => {
    if (callback) transcriptionCallbackRef.current = callback;
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
      let selectedType = '';
      for (const t of types) { if (MediaRecorder.isTypeSupported(t)) { selectedType = t; break; } }
      const recorder = new MediaRecorder(stream, selectedType ? { mimeType: selectedType } : undefined);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      recorder.ondataavailable = e => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      recorder.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: selectedType || 'audio/webm' });
        if (blob.size > 0) {
          setIsTranscribing(true);
          try {
            const formData = new FormData();
            formData.append('file', blob, 'recording.webm');
            const res = await APIClient.postMultipart<{ text: string }>(`/api/interviews/${interviewId}/transcribe`, formData, `tr-${Date.now()}`, 30000);
            if (res.text && transcriptionCallbackRef.current) transcriptionCallbackRef.current(res.text);
          } catch (e) {
             console.error('Transcription failed', e);
             toast.error('Voice transcription failed. You can type your response.');
          } finally { setIsTranscribing(false); }
        }
        stream.getTracks().forEach(t => t.stop());
      };
      recorder.start();
      setIsListening(true);
    }).catch(err => {
      console.error('Microphone access error:', err);
      toast.error('Microphone access denied or unavailable.');
    });
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isListening) {
      mediaRecorderRef.current.stop();
      setIsListening(false);
    }
  };

  // ─── PROCTORING SETUP ──────────────────────────────────────────────────────
  useEffect(() => {
    const setup = async () => {
      try {
        await tf.ready();
        detectorRef.current = await blazeface.load();
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        if (sessionVideoRef.current) sessionVideoRef.current.srcObject = stream;

        // Initialize session video recorder
        const types = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4'];
        let selectedType = '';
        for (const t of types) { if (MediaRecorder.isTypeSupported(t)) { selectedType = t; break; } }
        const vRecorder = new MediaRecorder(stream, selectedType ? { mimeType: selectedType } : undefined);
        videoRecorderRef.current = vRecorder;
        videoChunksRef.current = [];
        vRecorder.ondataavailable = (e) => { if (e.data.size > 0) videoChunksRef.current.push(e.data); };
        vRecorder.onstop = () => {
          const blob = new Blob(videoChunksRef.current, { type: selectedType || 'video/webm' });
          uploadVideo(blob);
        };
        vRecorder.start(10000); // chunk every 10s just in case

        faceCheckIntervalRef.current = setInterval(async () => {
          if (!sessionVideoRef.current || !detectorRef.current) return;
          const predictions = await detectorRef.current.estimateFaces(sessionVideoRef.current, false);
          setIsFaceDetected(predictions.length > 0);
          if (predictions.length === 0) handleStrike('Candidate not in frame');
          if (predictions.length > 1) handleStrike('Multiple people detected');
        }, 3000);
      } catch (e) { console.error('Video setup failed', e); }
    };
    setup();

    const handleVisibility = () => {
      if (document.hidden) handleStrike('Tab switched');
    };
    const handleBlur = () => handleStrike('Window focus lost');
    
    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('blur', handleBlur);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('blur', handleBlur);
      if (faceCheckIntervalRef.current) clearInterval(faceCheckIntervalRef.current);
      if (videoRecorderRef.current && videoRecorderRef.current.state !== 'inactive') {
        videoRecorderRef.current.stop();
      }
    };
  }, [handleStrike, uploadVideo]);

  // ─── RENDERS ───────────────────────────────────────────────────────────────
  if (isTerminated) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-md p-4">
        <Card className="max-w-md w-full border-destructive shadow-2xl text-center p-8 rounded-3xl">
          <ShieldAlert className="mx-auto w-16 h-16 text-destructive mb-6" />
          <CardTitle className="text-3xl font-black text-destructive mb-4">Session Terminated</CardTitle>
          <p className="text-slate-600 font-medium mb-8">This interview has been deactivated due to security violations.</p>
          <Button variant="outline" className="w-full h-14 rounded-2xl font-bold" onClick={() => window.location.href = '/calrims/'}>Return to Safety</Button>
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[80vh] space-y-6">
        <Loader2 className="w-12 h-12 animate-spin text-primary" />
        <h2 className="text-2xl font-black text-slate-800 tracking-tight">Initializing AI Board...</h2>
        <p className="text-slate-400 font-bold uppercase tracking-widest text-[10px]">Preparing Your Questions</p>
      </div>
    );
  }

  if (isFinished) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f8fafc] p-6">
        <Card className="max-w-3xl w-full bg-white shadow-2xl border-primary/20 rounded-3xl overflow-hidden animate-in zoom-in duration-500">
          <div className="h-2 bg-primary w-full" />
          <CardHeader className="text-center p-12">
            <ShieldCheck className="w-20 h-20 text-primary mx-auto mb-6" />
            <CardTitle className="text-4xl font-black text-slate-900">Assessment Complete</CardTitle>
            <p className="text-xl text-slate-500 font-medium mt-4">Your responses have been securely submitted and analyzed.</p>
          </CardHeader>
          <CardContent className="px-12 pb-12 text-center">
            <Button
              className="px-12 h-16 rounded-2xl font-black text-xl shadow-xl shadow-primary/20"
              onClick={() => window.location.href = '/calrims/'}
            >
              Exit & View Status
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-[#f8fafc]">
      <div className="flex flex-1 overflow-hidden">

        {/* Left Sidebar */}
        <div className="w-[320px] hidden lg:block border-r border-slate-100 bg-white">
          <InterviewSidebar
            currentQuestion={currentQuestionNumber}
            completedQuestions={completedQuestions}
            incorrectQuestions={incorrectQuestions}
            onSelectQuestion={jumpToQuestion}
            strikes={focusStrikes}
          />
        </div>

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto p-8 lg:p-12 relative no-scrollbar">
          <div className="max-w-5xl mx-auto space-y-10">

            {/* Header */}
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-4">
                <div className="p-3 rounded-2xl bg-white border border-slate-100 shadow-sm">
                  <BrainCircuit className="w-6 h-6 text-primary" />
                </div>
                <div>
                  <h1 className="text-2xl font-black text-slate-900 tracking-tight">Assessment Board</h1>
                  <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Secure Experience Protocol</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-100 rounded-xl shadow-sm">
                  <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  <span className="text-[10px] font-black text-slate-600 uppercase tracking-widest">Live Session</span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => window.location.href = '/calrims/'}
                  className="text-xs font-black text-slate-400 uppercase tracking-widest hover:text-red-500"
                >
                  End Session
                </Button>
              </div>
            </div>

            <QuestionPanel
              question={currentQuestion}
              isLoading={!currentQuestion || isEvaluating}
              currentQuestionNumber={currentQuestionNumber}
            />

            <AnswerInput
              onSubmit={handleSubmitAnswer}
              onPrev={currentQuestionNumber > 1 ? handlePrev : undefined}
              onNext={currentQuestionNumber < totalQuestions ? handleNext : undefined}
              disabled={!currentQuestion || isEvaluating}
              isEvaluating={isEvaluating}
              interviewId={interviewId}
              isListening={isListening}
              isTranscribing={isTranscribing}
              onStartRecording={startRecording}
              onStopRecording={stopRecording}
              isStuck={false}
              onRetry={() => {}}
              options={currentQuestion?.options}
              initialValue={currentQuestion?.answer_text}
            />

            {/* Status bar */}
            <div className="flex justify-between items-center pt-8 border-t border-slate-100">
              <div className="flex items-center gap-8">
                <div className="flex items-center gap-3">
                  <UserCheck className={`w-5 h-5 ${isFaceDetected ? 'text-green-500' : 'text-slate-300'}`} />
                  <div>
                    <div className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Identity</div>
                    <div className="text-xs font-bold text-slate-700">{isFaceDetected ? 'Verified' : 'Searching...'}</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Eye className={`w-5 h-5 ${isFocusingOnMonitor ? 'text-green-500' : 'text-amber-500'}`} />
                  <div>
                    <div className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Engagement</div>
                    <div className="text-xs font-bold text-slate-700">{isFocusingOnMonitor ? 'Optimal' : 'Flagged'}</div>
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Evaluation Engine</div>
                <div className="text-xs font-bold text-primary">{isEvaluating ? 'Analyzing Protocol...' : 'Standby'}</div>
              </div>
            </div>

          </div>
        </main>
      </div>

      {/* Floating Video Feed */}
      <div className="fixed bottom-8 right-8 w-64 aspect-video bg-slate-900 rounded-3xl border-4 border-white shadow-2xl overflow-hidden group z-50">
        <video
          ref={sessionVideoRef}
          autoPlay
          muted
          playsInline
          className={`w-full h-full object-cover transition-all duration-700 ${!isFaceDetected ? 'grayscale blur-sm' : ''}`}
        />
        <div className="absolute top-3 left-3 flex gap-1.5">
          <div className={`px-2 py-1 rounded-lg backdrop-blur-md border text-[8px] font-black uppercase tracking-tighter flex items-center gap-1.5 ${isFaceDetected ? 'bg-green-500/20 text-green-400 border-green-500/30' : 'bg-red-500/20 text-red-400 border-red-500/30'}`}>
            <div className={`w-1 h-1 rounded-full ${isFaceDetected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
            {isFaceDetected ? 'Live Proctor' : 'Sensor Alert'}
          </div>
        </div>
        {!isFaceDetected && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 backdrop-blur-[2px]">
            <ShieldAlert className="w-8 h-8 text-white animate-bounce" />
          </div>
        )}
      </div>
    </div>
  );
}
