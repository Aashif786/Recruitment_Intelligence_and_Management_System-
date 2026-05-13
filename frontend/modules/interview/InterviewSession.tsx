'use client';

import React, { useState, useEffect, useRef } from 'react';
import QuestionPanel from './QuestionPanel';
import AnswerInput from './AnswerInput';
import ScoreIndicator from './ScoreIndicator';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, ShieldAlert } from 'lucide-react';
import { APIClient } from '@/app/dashboard/lib/api-client';

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
  const [isConnected, setIsConnected] = useState(false);
  const [isFinished, setIsFinished] = useState(false);
  const [isTerminated, setIsTerminated] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState<{ question: string; difficulty: string } | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [latestFeedback, setLatestFeedback] = useState<{ score: number; text: string } | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evalHistory, setEvalHistory] = useState<any[]>([]);

  // Voice Recording States
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const transcriptionCallbackRef = useRef<((text: string) => void) | null>(null);

  // Voice Recording Refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const transcribeInFlightRef = useRef(false);
  const transcribeSeqRef = useRef(0);

  const ws = useRef<WebSocket | null>(null);
  /** True while any answer is queued or we are waiting for evaluation/error for the last sent item. */
  const answerInFlightRef = useRef(false);
  const answerQueueRef = useRef<QueuedAnswer[]>([]);
  const awaitingEvaluationRef = useRef(false);
  const currentQuestionRef = useRef<{ question: string; difficulty: string } | null>(null);

  const syncInFlightUi = () => {
    const busy = awaitingEvaluationRef.current || answerQueueRef.current.length > 0;
    answerInFlightRef.current = busy;
    setIsEvaluating(busy);
  };

  const flushAnswerQueue = () => {
    const conn = ws.current;
    if (!conn || conn.readyState !== WebSocket.OPEN) return;
    if (awaitingEvaluationRef.current) return;
    const next = answerQueueRef.current.shift();
    if (!next) {
      answerInFlightRef.current = false;
      setIsEvaluating(false);
      return;
    }
    awaitingEvaluationRef.current = true;
    answerInFlightRef.current = true;
    setIsEvaluating(true);
    conn.send(
      JSON.stringify({
        action: 'submit_answer',
        answer: next.text,
        request_id: next.requestId,
      }),
    );
  };

  useEffect(() => {
    currentQuestionRef.current = currentQuestion;
  }, [currentQuestion]);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = process.env.NEXT_PUBLIC_API_BASE_URL
      ? new URL(process.env.NEXT_PUBLIC_API_BASE_URL).host
      : '127.0.0.1:10000';
    const wsUrl = `${protocol}//${host}/ws/interview/${sessionId}?token=${token}`;

    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      setIsConnected(true);
      console.log('WebSocket connected');
    };

    ws.current.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (data.type) {
        case 'question':
          // New question invalidates any queued text (would target the wrong prompt).
          answerQueueRef.current = [];
          awaitingEvaluationRef.current = false;
          const q = { question: data.question, difficulty: data.difficulty };
          currentQuestionRef.current = q;
          setCurrentQuestion(q);
          setLatestFeedback(null);
          syncInFlightUi();
          break;
        case 'evaluation':
          awaitingEvaluationRef.current = false;
          setLatestFeedback({ score: data.score, text: data.feedback });
          const qText = currentQuestionRef.current?.question;
          setEvalHistory((prev) => [
            ...prev,
            {
              question: qText,
              score: data.score,
              feedback: data.feedback,
              timestamp: new Date().toLocaleTimeString(),
            },
          ]);
          flushAnswerQueue();
          break;
        case 'system':
          setMessages((prev) => [...prev, { text: data.message, type: 'system' }]);
          break;
        case 'end':
          answerQueueRef.current = [];
          awaitingEvaluationRef.current = false;
          answerInFlightRef.current = false;
          setIsEvaluating(false);
          setIsFinished(true);
          ws.current?.close();
          break;
        case 'error':
          awaitingEvaluationRef.current = false;
          // If the error message indicates a proctoring violation or termination
          if (data.message.toLowerCase().includes('terminated') || data.message.toLowerCase().includes('violation')) {
            setIsTerminated(true);
          }
          setMessages((prev) => [...prev, { text: data.message, type: 'error' }]);
          flushAnswerQueue();
          break;
      }
    };

    ws.current.onclose = () => {
      answerQueueRef.current = [];
      awaitingEvaluationRef.current = false;
      answerInFlightRef.current = false;
      setIsEvaluating(false);
      setIsConnected(false);
      console.log('WebSocket disconnected');
    };

    return () => {
      ws.current?.close();
    };
  }, [sessionId, token]);

  const handleSubmitAnswer = (answerText: string) => {
    const trimmed = answerText.trim();
    if (!trimmed) return;
    answerQueueRef.current.push({ text: trimmed, requestId: newRequestId() });
    syncInFlightUi();
    flushAnswerQueue();
  };

  // --- Voice Integration ---

  const startRecording = async (onTranscribed?: (text: string) => void) => {
    if (onTranscribed) transcriptionCallbackRef.current = onTranscribed;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Robust format detection
      const options = { mimeType: 'audio/webm' };
      let mediaRecorder: MediaRecorder;

      if (MediaRecorder.isTypeSupported('audio/webm')) {
        mediaRecorder = new MediaRecorder(stream, options);
      } else {
        mediaRecorder = new MediaRecorder(stream);
      }

      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const mimeType = mediaRecorder.mimeType || 'audio/webm';
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        if (audioBlob.size > 0) {
          await handleTranscribe(audioBlob);
        }
        // Stop all tracks to release the microphone
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start();
      setIsListening(true);
    } catch (err) {
      console.error('Microphone access denied', err);
      // In a real app we'd use toast, but InterviewSession doesn't have it directly. 
      // AnswerInput will handle errors if we pass them back or just alert.
      alert('Could not access microphone. Please check permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isListening) {
      mediaRecorderRef.current.stop();
      setIsListening(false);
    }
  };

  const handleTranscribe = async (audioBlob: Blob) => {
    if (transcribeInFlightRef.current) return;
    transcribeInFlightRef.current = true;
    setIsTranscribing(true);

    try {
      const formData = new FormData();
      const ext = audioBlob.type.includes('ogg') ? 'ogg' : 'webm';
      formData.append('file', audioBlob, `recording.${ext}`);

      transcribeSeqRef.current += 1;
      const rid = `live-${sessionId}-transcribe-${transcribeSeqRef.current}`;

      const res = await APIClient.postMultipart<{ text: string }>(
        `/api/interviews/${sessionId}/transcribe`,
        formData,
        rid,
      );

      if (res.text && res.text.trim()) {
        const result = res.text.trim();
        if (transcriptionCallbackRef.current) {
          transcriptionCallbackRef.current(result);
        }
      }
    } catch (err) {
      console.error('Transcription failed', err);
    } finally {
      setIsTranscribing(false);
      transcribeInFlightRef.current = false;
    }
  };

  if (isTerminated) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-md overflow-hidden p-4">
        <Card className="max-w-md w-full border-destructive shadow-2xl animate-in fade-in zoom-in duration-300 pointer-events-auto">
          <CardHeader className="text-center pb-2">
            <div className="mx-auto w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
              <ShieldAlert className="w-8 h-8 text-destructive" />
            </div>
            <CardTitle className="text-2xl font-bold text-destructive">Session Terminated</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-center">
            <p className="text-muted-foreground">
              This interview session has been automatically deactivated due to proctoring policy violations or focus detection strikes.
            </p>
            <div className="bg-destructive/5 p-3 rounded-lg border border-destructive/20 text-xs text-destructive font-medium uppercase tracking-wider">
              Security Protocol: V-3-STRIKES-ENGAGED
            </div>
            <Button 
                variant="outline" 
                className="w-full mt-4"
                onClick={() => window.location.href = '/dashboard/candidate'}
            >
              Return to Candidate Portal
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!isConnected && !isFinished) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 space-y-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <h2 className="text-xl font-semibold">Connecting to AI Interview Engine...</h2>
      </div>
    );
  }

  if (isFinished) {
    return (
      <div className="flex flex-col">
        <Card className="max-w-3xl mx-auto mt-12 bg-card border-primary/20 shadow-lg">
        <CardHeader>
          <CardTitle className="text-center text-3xl text-primary">Interview Complete</CardTitle>
        </CardHeader>
        <CardContent className="text-center space-y-6">
          <p className="text-lg text-muted-foreground">
            Thank you for completing the interview. The AI is generating your comprehensive profile.
          </p>
          <Button onClick={() => (window.location.href = '/dashboard/candidate')}>Return to Dashboard</Button>
        </CardContent>
      </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6 p-4 w-full">
      <div className="md:col-span-2 space-y-6">
        <QuestionPanel question={currentQuestion} isLoading={!currentQuestion} />

        <AnswerInput
          onSubmit={handleSubmitAnswer}
          disabled={!currentQuestion || isEvaluating || latestFeedback !== null}
          isEvaluating={isEvaluating}
          interviewId={sessionId}
          isListening={isListening}
          isTranscribing={isTranscribing}
          onStartRecording={startRecording}
          onStopRecording={stopRecording}
        />

        <div className="mt-8 p-4 border-t border-dashed bg-slate-50 border-slate-200 rounded-lg shadow-inner">
          <h3 className="text-sm font-bold text-slate-600 mb-2 flex items-center">
            <span className="w-2 h-2 bg-amber-500 rounded-full mr-2"></span>
            [Debug] Evaluation History Log
          </h3>
          {evalHistory.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">
              No evaluations logged yet. Submit an answer to view analysis in real-time.
            </p>
          ) : (
            <div className="space-y-4 max-h-96 overflow-y-auto">
              {evalHistory.map((item, idx) => (
                <div key={idx} className="bg-white p-3 rounded-lg border border-slate-200 shadow-sm space-y-2">
                  <div className="flex justify-between items-center text-xs text-slate-400">
                    <span className="font-semibold text-slate-500">Question {idx + 1}</span>
                    <span>{item.timestamp}</span>
                  </div>
                  <p className="text-sm font-medium text-slate-700">Q: {item.question}</p>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-full font-bold">
                      Score: {item.score}/10
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 bg-slate-50 p-2 rounded border border-slate-100">
                    Feedback: {item.feedback}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="space-y-6">
        <ScoreIndicator feedback={latestFeedback} currentDifficulty={currentQuestion?.difficulty} />

        <Card className="bg-muted/30">
          <CardHeader>
            <CardTitle className="text-sm">Session Log</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 h-64 overflow-y-auto text-sm">
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`p-2 rounded ${m.type === 'error' ? 'bg-destructive/10 text-destructive' : 'bg-secondary/50 text-secondary-foreground'}`}
              >
                {m.text}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
    </div>
  );
}
