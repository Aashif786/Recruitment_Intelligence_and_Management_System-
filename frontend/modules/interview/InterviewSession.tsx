'use client';

import React, { useState, useEffect, useRef } from 'react';
import QuestionPanel from './QuestionPanel';
import AnswerInput from './AnswerInput';
import ScoreIndicator from './ScoreIndicator';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { API_BASE_URL } from '@/lib/config';
import { toast } from 'sonner';
import { APIClient } from '@/app/dashboard/lib/api-client';

// Face Detection Imports (Modern Logic)
import * as tf from '@tensorflow/tfjs-core';
import '@tensorflow/tfjs-backend-webgl';
import * as blazeface from '@tensorflow-models/blazeface';
import { 
  Loader2, ShieldCheck, ShieldAlert, AlertTriangle, 
  UserSearch, Mic, MicOff, Send, Camera, CameraOff,
  UserCheck, Users, Eye, EyeOff, BrainCircuit
} from 'lucide-react';
import InterviewSidebar from './InterviewSidebar';

interface InterviewSessionProps {
  sessionId: string;
  token: string;
}

type QueuedAnswer = { text: string; requestId: string };

function newRequestId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `r-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

export default function InterviewSession({ sessionId, token }: InterviewSessionProps) {
  // --- CORE INTERVIEW STATES ---
  const [isConnected, setIsConnected] = useState(false);
  const [isFinished, setIsFinished] = useState(false);
  const [isTerminated, setIsTerminated] = useState(false);
  const [focusStrikes, setFocusStrikes] = useState(0);
  
  const [totalQuestions, setTotalQuestions] = useState(30);
  const [currentQuestionNumber, setCurrentQuestionNumber] = useState(1);
  const [currentQuestion, setCurrentQuestion] = useState<{ 
    question: string; 
    difficulty: string; 
    options?: string[];
    answer_text?: string | null;
  } | null>(null);
  
  const [completedQuestions, setCompletedQuestions] = useState<number[]>([]);
  const [incorrectQuestions, setIncorrectQuestions] = useState<number[]>([]);
  const [messages, setMessages] = useState<any[]>([]);
  const [latestFeedback, setLatestFeedback] = useState<{ score: number; text: string } | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [isEvaluationStuck, setIsEvaluationStuck] = useState(false);

  // --- PROCTORING STATES ---
  const [isFaceDetected, setIsFaceDetected] = useState(true);
  const [isFocusingOnMonitor, setIsFocusingOnMonitor] = useState(true);
  
  // --- REFS ---
  const ws = useRef<WebSocket | null>(null);
  const answerQueueRef = useRef<QueuedAnswer[]>([]);
  const awaitingEvaluationRef = useRef(false);
  const currentQuestionRef = useRef<any>(null);
  const sessionStartRef = useRef(Date.now());
  const evaluationTimerRef = useRef<any>(null);
  
  // Video & Audio Refs
  const detectorRef = useRef<any>(null);
  const faceCheckIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const sessionVideoRef = useRef<HTMLVideoElement>(null);
  
  // Voice Recording Logic
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const transcriptionCallbackRef = useRef<((text: string) => void) | null>(null);

  // --- LOGIC HANDLERS ---
  
  const handleStrike = (reason: string) => {
    if (Date.now() - sessionStartRef.current < 10000) return;

    setFocusStrikes(prev => {
        const next = prev + 1;
        console.error(`[SECURITY] Strike ${next}/3: ${reason}`);
        setMessages(m => [...m, { type: 'error', text: `SECURITY ALERT: ${reason} (Strike ${next}/3)` }]);
        if (next >= 3) {
            setIsTerminated(true);
            ws.current?.send(JSON.stringify({ action: 'security_violation', reason }));
        }
        return next;
    });
  };

  const jumpToQuestion = (num: number) => {
    if (num < 1 || num > totalQuestions) return;
    if (isEvaluating) {
        toast.warning("Please wait for AI evaluation to complete.");
        return;
    }
    ws.current?.send(JSON.stringify({ action: 'jump_to_question', number: num }));
  };

  const handleNext = () => currentQuestionNumber < totalQuestions && jumpToQuestion(currentQuestionNumber + 1);
  const handlePrev = () => currentQuestionNumber > 1 && jumpToQuestion(currentQuestionNumber - 1);

  const flushAnswerQueue = () => {
    const conn = ws.current;
    if (!conn || conn.readyState !== WebSocket.OPEN || awaitingEvaluationRef.current) return;
    
    const next = answerQueueRef.current.shift();
    if (!next) {
      setIsEvaluating(false);
      return;
    }

    awaitingEvaluationRef.current = true;
    setIsEvaluating(true);
    conn.send(JSON.stringify({
      action: 'submit_answer',
      answer: next.text,
      request_id: next.requestId,
    }));

    if (evaluationTimerRef.current) clearTimeout(evaluationTimerRef.current);
    evaluationTimerRef.current = setTimeout(() => setIsEvaluationStuck(true), 30000);
  };

  const handleSubmitAnswer = (text: string) => {
    if (!text.trim()) return;
    setLatestFeedback(null);
    answerQueueRef.current.push({ text, requestId: newRequestId() });
    flushAnswerQueue();
  };

  // --- TRANSCRIPTION ---
  const startRecording = (callback?: (text: string) => void) => {
    if (callback) transcriptionCallbackRef.current = callback;
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      recorder.ondataavailable = e => audioChunksRef.current.push(e.data);
      recorder.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        if (blob.size > 0) {
            setIsTranscribing(true);
            try {
                const formData = new FormData();
                formData.append('file', blob, 'recording.webm');
                const res = await APIClient.postMultipart<{ text: string }>(`/api/interviews/${sessionId}/transcribe`, formData, `tr-${Date.now()}`);
                if (res.text && transcriptionCallbackRef.current) transcriptionCallbackRef.current(res.text);
            } finally {
                setIsTranscribing(false);
            }
        }
        stream.getTracks().forEach(t => t.stop());
      };
      recorder.start();
      setIsListening(true);
    }).catch(() => toast.error("Microphone access denied."));
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isListening) {
      mediaRecorderRef.current.stop();
      setIsListening(false);
    }
  };

  // --- EFFECT: WEBSOCKET ---
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let wsBase = API_BASE_URL.replace(/^https?:\/\//, protocol + '//');
    if (wsBase.endsWith('/')) wsBase = wsBase.slice(0, -1);
    const wsUrl = `${wsBase}/ws/interview/${sessionId}?token=${token}`;
    
    ws.current = new WebSocket(wsUrl);
    ws.current.onopen = () => {
        setIsConnected(true);
        ws.current?.send(JSON.stringify({ action: 'start' }));
    };

    ws.current.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'question') {
            const qData = { 
                question: data.question, 
                difficulty: data.difficulty || 'medium',
                options: data.options,
                answer_text: data.answer_text
            };
            setCurrentQuestion(qData);
            currentQuestionRef.current = qData;
            setCurrentQuestionNumber(data.question_number || 1);
            setTotalQuestions(data.total_questions || 30);
            setIsEvaluating(false);
            awaitingEvaluationRef.current = false;
            if (data.answer_text) {
                setCompletedQuestions(prev => [...new Set([...prev, data.question_number])]);
                if (data.score !== undefined && data.score < 5) {
                    setIncorrectQuestions(prev => [...new Set([...prev, data.question_number])]);
                }
            }
            if (evaluationTimerRef.current) clearTimeout(evaluationTimerRef.current);
            setIsEvaluationStuck(false);
        } else if (data.type === 'evaluation') {
            awaitingEvaluationRef.current = false;
            setIsEvaluating(false);
            setLatestFeedback({ score: data.score, text: data.feedback });
            setCompletedQuestions(prev => [...new Set([...prev, currentQuestionNumber])]);
            if (data.score < 5) setIncorrectQuestions(prev => [...new Set([...prev, currentQuestionNumber])]);
            if (evaluationTimerRef.current) clearTimeout(evaluationTimerRef.current);
            setIsEvaluationStuck(false);
            flushAnswerQueue();
        } else if (data.type === 'system') {
            setMessages(prev => [...prev, { type: 'system', text: data.message }]);
        } else if (data.type === 'end') {
            setIsFinished(true);
        }
    };

    return () => ws.current?.close();
  }, [sessionId, token]);

  // --- EFFECT: PROCTORING ---
  useEffect(() => {
    const setup = async () => {
        try {
            await tf.ready();
            detectorRef.current = await blazeface.load();
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            if (sessionVideoRef.current) {
                sessionVideoRef.current.srcObject = stream;
            }
            faceCheckIntervalRef.current = setInterval(async () => {
                if (!sessionVideoRef.current || !detectorRef.current) return;
                const predictions = await detectorRef.current.estimateFaces(sessionVideoRef.current, false);
                setIsFaceDetected(predictions.length > 0);
                if (predictions.length === 0) handleStrike('Candidate not in frame');
                if (predictions.length > 1) handleStrike('Multiple people detected');
            }, 3000);
        } catch (e) {
            console.error("Video setup failed", e);
        }
    };
    setup();
    const handleTab = () => document.hidden && handleStrike('Tab focus lost');
    document.addEventListener('visibilitychange', handleTab);
    return () => {
        document.removeEventListener('visibilitychange', handleTab);
        if (faceCheckIntervalRef.current) clearInterval(faceCheckIntervalRef.current);
    };
  }, []);

  // --- RENDERS ---

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

  if (!isConnected && !isFinished) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[80vh] space-y-6">
        <Loader2 className="w-12 h-12 animate-spin text-primary" />
        <h2 className="text-2xl font-black text-slate-800 tracking-tight">Initializing Classic AI Board...</h2>
        <p className="text-slate-400 font-bold uppercase tracking-widest text-[10px]">Secure Handshake in Progress</p>
      </div>
    );
  }

  if (isFinished) {
    return (
      <Card className="max-w-3xl mx-auto mt-24 shadow-2xl border-primary/20 rounded-3xl overflow-hidden animate-in zoom-in duration-500">
        <div className="h-2 bg-primary w-full" />
        <CardHeader className="text-center p-12">
            <ShieldCheck className="w-20 h-20 text-primary mx-auto mb-6" />
            <CardTitle className="text-4xl font-black text-slate-900">Assessment Complete</CardTitle>
            <p className="text-xl text-slate-500 font-medium mt-4">Your responses have been securely submitted and analyzed.</p>
        </CardHeader>
        <CardContent className="px-12 pb-12 text-center">
          <Button className="px-12 h-16 rounded-2xl font-black text-xl shadow-xl shadow-primary/20" onClick={() => window.location.href = '/calrims/'}>Exit & View Status</Button>
        </CardContent>
      </Card>
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
        <main className="flex-1 overflow-y-auto p-8 lg:p-12 relative">
            <div className="max-w-5xl mx-auto space-y-10">
                <div className="flex justify-between items-center">
                    <div className="flex items-center gap-4">
                        <div className="p-3 rounded-2xl bg-white border border-slate-100 shadow-sm">
                            <BrainCircuit className="w-6 h-6 text-primary" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-black text-slate-900 tracking-tight">RIMS Assessment Board</h1>
                            <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Connected Experience Protocol</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-100 rounded-xl shadow-sm">
                            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                            <span className="text-[10px] font-black text-slate-600 uppercase tracking-widest">Sync Active</span>
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
                    interviewId={sessionId}
                    isListening={isListening}
                    isTranscribing={isTranscribing}
                    onStartRecording={startRecording}
                    onStopRecording={stopRecording}
                    isStuck={isEvaluationStuck}
                    onRetry={() => { setIsEvaluationStuck(false); flushAnswerQueue(); }}
                    options={currentQuestion?.options}
                    initialValue={currentQuestion?.answer_text}
                />

                <div className="flex justify-between items-center pt-8 border-t border-slate-100">
                    <div className="flex items-center gap-8">
                        <div className="flex items-center gap-3">
                            <UserCheck className={`w-5 h-5 ${isFaceDetected ? 'text-green-500' : 'text-slate-300'}`} />
                            <div>
                                <div className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Candidate</div>
                                <div className="text-xs font-bold text-slate-700">{isFaceDetected ? 'Verified' : 'Detecting...'}</div>
                            </div>
                        </div>
                        <div className="flex items-center gap-3">
                            <Eye className={`w-5 h-5 ${isFocusingOnMonitor ? 'text-green-500' : 'text-amber-500'}`} />
                            <div>
                                <div className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Focus</div>
                                <div className="text-xs font-bold text-slate-700">{isFocusingOnMonitor ? 'On Screen' : 'Distracted'}</div>
                            </div>
                        </div>
                    </div>
                    <div className="text-right">
                        <div className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">AI Evaluation</div>
                        <div className="text-xs font-bold text-blue-600">{isEvaluating ? 'Analyzing Response...' : 'Ready'}</div>
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
                  {isFaceDetected ? 'Proctor Active' : 'Face Missing'}
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
