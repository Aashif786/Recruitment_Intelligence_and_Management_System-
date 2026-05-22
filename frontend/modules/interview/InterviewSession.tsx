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
  const [isStarted, setIsStarted] = useState(false);  // candidate clicked start
  const [isReady, setIsReady] = useState(false);       // questions loaded
  const [isLoading, setIsLoading] = useState(true);    // first load spinner
  const [isFinished, setIsFinished] = useState(false);
  const [isTerminated, setIsTerminated] = useState(false);
  const [pollingError, setPollingError] = useState<string | null>(null);
  const [pollTrigger, setPollTrigger] = useState(0);
  const [focusStrikes, setFocusStrikes] = useState<number>(() => {
    if (typeof window !== 'undefined') {
      const saved = sessionStorage.getItem(`strikes_${sessionId}`);
      return saved ? parseInt(saved, 10) : 0;
    }
    return 0;
  });
  const sessionStartRef = useRef(Date.now());

  // ── question state ──
  const [allQuestions, setAllQuestions] = useState<any[]>([]);
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
  const activeStreamRef = useRef<MediaStream | null>(null);
  const isSubmittingRef = useRef(false);

  // ─── SECURITY VIOLATION ────────────────────────────────────────────────────
  const terminationSentRef = useRef(false);

  const handleStrike = useCallback((reason: string) => {
    if (!isStarted) return; // ignore strikes before session officially starts
    if (Date.now() - sessionStartRef.current < 15000) return; // ignore first 15s

    setFocusStrikes(prev => {
      const next = prev + 1;
      if (typeof window !== 'undefined') {
        sessionStorage.setItem(`strikes_${interviewId}`, next.toString());
      }

      // Record strike as a monitoring event to create a server-side audit trail
      const sanitizedReason = reason.replace(/\s+/g, '_').toLowerCase();
      fetch(`${API_BASE_URL}/api/interviews/${interviewId}/monitoring-events`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({
          event_type: `focus_lost_strike_${next}_${sanitizedReason}`,
          confidence_score: 0.0,
        }),
      }).catch((err) => console.error('Failed to post strike monitoring event:', err));

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
  }, [interviewId, token, isStarted]);

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
            options: q.options ? JSON.parse(q.options) : (q.question_options ? JSON.parse(q.question_options) : undefined),
            answer_text: q.answer_text,
            question_type: q.question_type,
          });
          setCurrentQuestionNumber(q.question_number);
          const answered = all.filter((x: any) => x.is_answered).map((x: any) => x.question_number);
          const incorrect = all.filter((x: any) => x.is_answered && x.answer_score !== null && x.answer_score < 5).map((x: any) => x.question_number);
          setCompletedQuestions(answered);
          setIncorrectQuestions(incorrect);
          setTotalQuestions(all.length);
          setAllQuestions(all);
        }
      } else {
        // Get current unanswered question
        const res = await apiFetch(`/api/interviews/${interviewId}/current-question`, token);
        if (res.status === 'processing' || !res.id) return;
        setCurrentQuestion({
          id: res.id,
          question: res.question_text,
          difficulty: 'medium',
          options: res.options ? JSON.parse(res.options) : (res.question_options ? JSON.parse(res.question_options) : undefined),
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
    let pollCount = 0;
    const maxPolls = 60; // 60 * 2.5s = 150 seconds (2.5 minutes)

    const poll = async () => {
      if (cancelled) return;
      try {
        const stage = await apiFetch(`/api/interviews/${interviewId}/stage`, token);
        if (stage.status === 'processing' || !stage.questions_ready) {
          pollCount += 1;
          if (pollCount >= maxPolls) {
            setPollingError("We're experiencing delays preparing your interview questions. Please try again or contact support.");
            setIsLoading(false);
            return;
          }
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
          setAllQuestions(all);
          await loadCurrentQuestion();
          setIsReady(true);
          setIsLoading(false);
        }
      } catch (e: any) {
        pollCount += 1;
        if (pollCount >= maxPolls) {
          setPollingError("An error occurred while connecting to the interview server. Please check your connection and retry.");
          setIsLoading(false);
          return;
        }
        if (!cancelled) setTimeout(poll, 3000);
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [interviewId, token, loadCurrentQuestion, pollTrigger]);

  const handleRetryPoll = () => {
    setPollingError(null);
    setIsLoading(true);
    setPollTrigger(prev => prev + 1);
  };

  // ─── SUBMIT ANSWER ─────────────────────────────────────────────────────────
  const handleSubmitAnswer = async (text: string) => {
    if (!text.trim() || !currentQuestion) return;
    if (isSubmittingRef.current) {
      console.warn('Submission already in progress, ignoring duplicate submit.');
      return;
    }
    isSubmittingRef.current = true;
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

      const newlyCompleted = [...new Set([...completedQuestions, currentQuestionNumber])];
      setCompletedQuestions(newlyCompleted);
      addMsg('Response recorded. Loading next question...');

      // Small visual delay so the question turns green in the UI before transitioning
      await new Promise(resolve => setTimeout(resolve, 1000));

      const aptitudeQuestions = allQuestions.filter(q => q.question_type === 'aptitude');
      const allAptitudeCompleted = aptitudeQuestions.length > 0 && aptitudeQuestions.every(q => newlyCompleted.includes(q.question_number));

      if (allAptitudeCompleted && currentQuestion.question_type === 'aptitude') {
        // Complete the aptitude round
        await apiFetch(`/api/interviews/${interviewId}/complete-aptitude`, token, { method: 'POST' }).catch(() => null);
        
        // Refresh question list to get the new technical questions
        const updatedQuestions: any[] = await apiFetch(`/api/interviews/${interviewId}/questions`, token);
        setAllQuestions(updatedQuestions);
        setTotalQuestions(updatedQuestions.length);
        
        const firstTech = updatedQuestions.find(q => q.question_type !== 'aptitude');
        if (firstTech) {
           await loadCurrentQuestion(firstTech.question_number);
        } else {
           setIsFinished(true);
        }
      } else {
        // Show next question
        const nextNum = currentQuestionNumber + 1;
        await loadCurrentQuestion(nextNum).catch(() => setIsFinished(true));
      }

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
          setAllQuestions(all);
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
      isSubmittingRef.current = false;
    }
  };

  // ─── END SESSION ──────────────────────────────────────────────────────────
  const handleEndSession = async () => {
    const confirmed = window.confirm("Are you sure you want to end this interview session? Your progress will be saved, but you won't be able to return to it.");
    if (!confirmed) return;

    try {
      await apiFetch(`/api/interviews/${interviewId}/end`, token, {
        method: 'POST',
        body: JSON.stringify({ force: true, ended_early: true }),
      });
      setIsFinished(true);
    } catch (err: any) {
      toast.error('Failed to end interview session properly. Exiting to dashboard...');
      setTimeout(() => {
        window.location.href = '/calrims/';
      }, 1500);
    }
  };

  const isQuestionLocked = useCallback((qNum: number) => {
    const targetQ = allQuestions.find(q => q.question_number === qNum);
    if (!targetQ) return true;
    
    // Group all questions by type
    const groups: Record<string, any[]> = {};
    allQuestions.forEach((q) => {
      const type = (q.question_type || 'General').toLowerCase();
      if (!groups[type]) groups[type] = [];
      groups[type].push(q);
    });
    
    const orderedTypes = ['aptitude', 'technical', 'behavioral'];
    const otherTypes = Object.keys(groups).filter(t => !orderedTypes.includes(t));
    const displayOrder = [...orderedTypes, ...otherTypes];
    
    const targetType = (targetQ.question_type || 'General').toLowerCase();
    const targetTypeIdx = displayOrder.indexOf(targetType);
    
    // Check if any previous type has incomplete questions
    for (let i = 0; i < targetTypeIdx; i++) {
      const prevType = displayOrder[i];
      const prevGroup = groups[prevType];
      if (prevGroup && prevGroup.length > 0) {
        const hasIncomplete = prevGroup.some(q => !completedQuestions.includes(q.question_number));
        if (hasIncomplete) {
          return true;
        }
      }
    }
    return false;
  }, [allQuestions, completedQuestions]);

  // ─── NAVIGATION ───────────────────────────────────────────────────────────
  const jumpToQuestion = useCallback(async (num: number) => {
    if (!allQuestions.find(q => q.question_number === num)) return;
    if (isEvaluating) { toast.warning('Please wait for evaluation to complete.'); return; }
    if (isQuestionLocked(num)) {
      toast.warning('Please complete all questions in the current section first.');
      return;
    }
    setIsLoading(true);
    await loadCurrentQuestion(num);
    setIsLoading(false);
  }, [totalQuestions, isEvaluating, loadCurrentQuestion, allQuestions, isQuestionLocked]);

  const handleNext = () => {
    const nextQ = [...allQuestions].sort((a,b) => a.question_number - b.question_number).find(q => q.question_number > currentQuestionNumber);
    if (nextQ) {
      if (isQuestionLocked(nextQ.question_number)) {
        toast.warning('Please complete all questions in the current section first.');
        return;
      }
      jumpToQuestion(nextQ.question_number);
    }
  };
  const handlePrev = () => {
    const prevQ = [...allQuestions].sort((a,b) => b.question_number - a.question_number).find(q => q.question_number < currentQuestionNumber);
    if (prevQ) {
      if (isQuestionLocked(prevQ.question_number)) {
        toast.warning('Please complete all questions in the current section first.');
        return;
      }
      jumpToQuestion(prevQ.question_number);
    }
  };

  // ─── TRANSCRIPTION ─────────────────────────────────────────────────────────
  const startRecording = (callback?: (text: string) => void) => {
    if (callback) transcriptionCallbackRef.current = callback;
    setIsListening(true);
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
        // Stop the stream tracks instantly so the browser mic indicator turns off immediately, preventing device locking
        stream.getTracks().forEach(t => t.stop());
        
        if (blob.size > 500) {
          setIsTranscribing(true);
          try {
            const formData = new FormData();
            formData.append('file', blob, 'recording.webm');
            const res = await APIClient.postMultipart<{ text: string }>(`/api/interviews/${interviewId}/transcribe`, formData, `tr-${Date.now()}`, 15000);
            if (res.text) {
              if (transcriptionCallbackRef.current) transcriptionCallbackRef.current(res.text);
            } else {
              toast.error("Transcription returned empty. Please speak clearly or check your mic.");
            }
          } catch (e: any) {
             console.error('Transcription failed', e);
             const errorMsg = e.message || String(e);
             const isTerminatedError = errorMsg.toLowerCase().includes('terminated') || 
                                     errorMsg.toLowerCase().includes('proctoring violation');
             
             if (isTerminatedError) {
               toast.error('Voice service is unavailable as the session has been terminated.');
               setIsTerminated(true);
             } else {
               toast.error('Voice transcription failed. You can type your response.');
             }
          } finally { setIsTranscribing(false); }
        } else if (blob.size > 0) {
          toast.error("Audio recording was too short or silent. Please try again.");
        }
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
  const cameraInitializedRef = useRef(false);

  useEffect(() => {
    async function initCamera() {
      if (cameraInitializedRef.current) return;
      
      try {
        await tf.ready();
        if (!detectorRef.current) {
          detectorRef.current = await blazeface.load();
        }

        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        activeStreamRef.current = stream;
        if (sessionVideoRef.current) sessionVideoRef.current.srcObject = stream;
        cameraInitializedRef.current = true;

        const videoTrack = stream.getVideoTracks()[0];
        if (videoTrack) {
          videoTrack.onmute = () => handleStrike('Camera feed disabled/muted');
          videoTrack.onended = () => {
            handleStrike('Camera hardware disconnected');
          };
        }

        const audioTrack = stream.getAudioTracks()[0];
        if (audioTrack) {
          audioTrack.onmute = () => handleStrike('Microphone feed disabled/muted');
          audioTrack.onended = () => {
            handleStrike('Microphone hardware disconnected');
          };
          
          try {
            const AudioContext = window.AudioContext || (window as any).webkitAudioContext;
            if (AudioContext) {
              const audioCtx = new AudioContext();
              const analyser = audioCtx.createAnalyser();
              const source = audioCtx.createMediaStreamSource(stream);
              source.connect(analyser);
              analyser.fftSize = 256;
              const dataArray = new Uint8Array(analyser.frequencyBinCount);
              
              const updateVolume = () => {
                if (cameraInitializedRef.current === false) return; // stopped
                analyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for(let i=0; i<dataArray.length; i++) sum += dataArray[i];
                const avg = sum / dataArray.length;
                const volBar = document.getElementById('mic-volume-bar');
                if (volBar) {
                  volBar.style.width = Math.min(100, (avg / 64) * 100) + '%';
                }
                requestAnimationFrame(updateVolume);
              };
              updateVolume();
            }
          } catch(e) {
            console.error('AudioContext setup failed', e);
          }
        }
      } catch (e) {
        console.error('Video setup failed', e);
      }
    }
    
    initCamera();

    return () => {
      // We only stop tracks if the component completely unmounts (leaving the interview)
      if (activeStreamRef.current) {
        activeStreamRef.current.getTracks().forEach(t => t.stop());
      }
    };
  }, [handleStrike]); // Only run on mount, but depends on handleStrike

  // Synchronize camera stream to video element when isStarted changes
  useEffect(() => {
    if (sessionVideoRef.current && activeStreamRef.current) {
      if (sessionVideoRef.current.srcObject !== activeStreamRef.current) {
        sessionVideoRef.current.srcObject = activeStreamRef.current;
        console.log("Attached active camera stream to current video element.");
      }
    }
  }, [isStarted]);

  // Proctoring monitors & Video recorder (Runs when isStarted becomes true)
  useEffect(() => {
    if (!isStarted || !activeStreamRef.current) return;

    let checkCount = 0;
    const stream = activeStreamRef.current;

    // Initialize session video recorder
    if (videoRecorderRef.current && videoRecorderRef.current.state !== 'inactive') {
      try { videoRecorderRef.current.stop(); } catch (e) { console.error(e); }
    }

    let vRecorder: MediaRecorder | null = null;
    try {
      const types = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4'];
      let selectedType = '';
      for (const t of types) { if (MediaRecorder.isTypeSupported(t)) { selectedType = t; break; } }
      vRecorder = new MediaRecorder(stream, selectedType ? { mimeType: selectedType } : undefined);
    } catch (e) {
      console.warn("Failed to create MediaRecorder with types, trying default option:", e);
      try {
        vRecorder = new MediaRecorder(stream);
      } catch (err) {
        console.error("Failed to create default MediaRecorder:", err);
      }
    }

    if (vRecorder) {
      videoRecorderRef.current = vRecorder;
      videoChunksRef.current = [];
      vRecorder.ondataavailable = (e) => { if (e.data.size > 0) videoChunksRef.current.push(e.data); };
      vRecorder.onstop = () => {
        const blob = new Blob(videoChunksRef.current, { type: vRecorder?.mimeType || 'video/webm' });
        uploadVideo(blob);
      };
      try {
        vRecorder.start(10000); // chunk every 10s just in case
      } catch (startErr) {
        console.error("Failed to start MediaRecorder:", startErr);
        toast.error("Video recording could not be started, but your interview session is safe to continue.", {
          description: "Webcam monitoring and proctoring remain fully active."
        });
      }
    }

    if (faceCheckIntervalRef.current) clearInterval(faceCheckIntervalRef.current);
    faceCheckIntervalRef.current = setInterval(async () => {
      const video = sessionVideoRef.current;
      if (!video || !detectorRef.current) return;
      if (video.readyState < 2 || video.videoWidth === 0) return;
      
      try {
        const predictions = await detectorRef.current.estimateFaces(video, false);
        const faceFound = predictions.length > 0;
        setIsFaceDetected(faceFound);

        if (predictions.length === 0) {
          handleStrike('Candidate not in frame');
        } else if (predictions.length > 1) {
          handleStrike('Multiple people detected');
        }

        checkCount++;
        if (checkCount >= 5) {
          checkCount = 0;
          const statusType = predictions.length === 1 ? 'normal' : (predictions.length === 0 ? 'face_not_detected' : 'multiple_people');
          const confidence = predictions.length === 1 ? 1.0 : 0.0;
          fetch(`${API_BASE_URL}/api/interviews/${interviewId}/monitoring-events`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              event_type: statusType,
              confidence_score: confidence,
            }),
          }).catch(() => {});
        }
      } catch (err) {
        console.error('Face check error:', err);
      }
    }, 3000);

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
        try { videoRecorderRef.current.stop(); } catch (e) {}
      }
    };
  }, [isStarted, interviewId, token, handleStrike, uploadVideo]);


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

  if (pollingError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f8fafc] p-6 animate-in zoom-in duration-500">
        <Card className="max-w-md w-full bg-white shadow-2xl border-destructive/20 rounded-3xl overflow-hidden">
          <div className="h-2 bg-destructive w-full" />
          <CardHeader className="text-center p-8 pb-4">
            <ShieldAlert className="mx-auto w-16 h-16 text-destructive mb-4 animate-bounce" />
            <CardTitle className="text-2xl font-black text-slate-800 tracking-tight">Initialization Delay</CardTitle>
          </CardHeader>
          <CardContent className="px-8 pb-8 space-y-6 text-center">
            <p className="text-slate-600 font-medium text-sm leading-relaxed">
              {pollingError}
            </p>
            <div className="flex flex-col gap-3 pt-2">
              <Button
                className="w-full h-14 rounded-2xl font-black text-base shadow-lg shadow-primary/20"
                onClick={handleRetryPoll}
              >
                Retry Initialization
              </Button>
              <Button
                variant="outline"
                className="w-full h-14 rounded-2xl font-bold text-slate-500 hover:text-slate-700"
                onClick={() => window.location.href = '/calrims/'}
              >
                Go Back to Dashboard
              </Button>
            </div>
          </CardContent>
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

  if (!isStarted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f8fafc] p-6">
        <Card className="max-w-3xl w-full bg-white shadow-2xl border-primary/20 rounded-3xl overflow-hidden animate-in zoom-in duration-500">
          <div className="h-2 bg-primary w-full" />
          <CardHeader className="text-center p-12 pb-6">
            <BrainCircuit className="w-20 h-20 text-primary mx-auto mb-6" />
            <CardTitle className="text-4xl font-black text-slate-900">Ready to Begin?</CardTitle>
            <p className="text-xl text-slate-500 font-medium mt-4 italic">"True intelligence is the ability to adapt to change."</p>
          </CardHeader>
          <CardContent className="px-12 space-y-8">
            {/* Live Camera Preview */}
            <div className="flex flex-col items-center justify-center">
              <div className="w-full max-w-md aspect-video bg-slate-900 rounded-2xl border border-slate-100 shadow-inner overflow-hidden relative">
                <video
                  ref={sessionVideoRef}
                  autoPlay
                  muted
                  playsInline
                  className="w-full h-full object-cover"
                />
                <div className="absolute bottom-4 left-4 right-4 flex justify-between items-center bg-black/40 backdrop-blur-md px-4 py-2 rounded-xl text-white">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    <span className="text-[10px] font-black uppercase tracking-widest text-white/90">Camera Preview</span>
                  </div>
                  <span className="text-[9px] font-bold text-white/70">Verify framing before entering</span>
                </div>
              </div>

              {/* Microphone Volume Indicator */}
              <div className="w-full max-w-md mt-4 p-4 bg-slate-50 rounded-2xl border border-slate-100 flex flex-col gap-2">
                <div className="flex justify-between items-center w-full">
                   <span className="text-xs font-black text-slate-800 uppercase tracking-widest">Microphone Test</span>
                   <span className="text-[10px] font-bold text-slate-400">Speak to check levels</span>
                </div>
                <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                   <div id="mic-volume-bar" className="h-full bg-blue-500 transition-all duration-100 ease-out" style={{ width: '0%' }} />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="p-6 bg-slate-50 rounded-2xl border border-slate-100">
                <h3 className="font-black text-slate-800 uppercase tracking-widest text-xs mb-3">Session Secure</h3>
                <p className="text-sm text-slate-500 font-medium leading-relaxed">System will monitor your window focus to ensure interview integrity.</p>
              </div>
              <div className="p-6 bg-slate-50 rounded-2xl border border-slate-100">
                <h3 className="font-black text-slate-800 uppercase tracking-widest text-xs mb-3">Session Recording</h3>
                <p className="text-sm text-slate-500 font-medium leading-relaxed">Video and audio will be recorded for HR review. Ensure a quiet, well-lit environment.</p>
              </div>
            </div>
            <div className="flex flex-col items-center gap-4 pt-4">
              <Button
                className="w-full h-16 rounded-2xl font-black text-xl shadow-xl shadow-primary/20"
                onClick={() => {
                  sessionStartRef.current = Date.now();
                  setIsStarted(true);
                }}
              >
                Enter Interview Board
              </Button>
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">By clicking, you agree to the assessment monitoring protocol</p>
            </div>
          </CardContent>
        </Card>
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
            allQuestions={allQuestions}
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
                  onClick={handleEndSession}
                  className="text-xs font-black text-slate-400 uppercase tracking-widest hover:text-red-500"
                >
                  End Session
                </Button>
              </div>
            </div>
            
            {(() => {
               let relNum = currentQuestionNumber;
               if (allQuestions && currentQuestion) {
                 const sameType = allQuestions.filter(q => q.question_type === currentQuestion.question_type)
                                              .sort((a, b) => a.question_number - b.question_number);
                 const idx = sameType.findIndex(q => q.question_number === currentQuestionNumber);
                 if (idx >= 0) relNum = idx + 1;
               }
               return (
                 <QuestionPanel
                   question={currentQuestion}
                   isLoading={!currentQuestion || isEvaluating}
                   currentQuestionNumber={relNum}
                 />
               );
            })()}

            <AnswerInput
              onSubmit={handleSubmitAnswer}
              onPrev={([...allQuestions].sort((a,b) => a.question_number - b.question_number)[0]?.question_number < currentQuestionNumber) ? handlePrev : undefined}
              onNext={([...allQuestions].sort((a,b) => b.question_number - a.question_number)[0]?.question_number > currentQuestionNumber) ? handleNext : undefined}
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
              isSubmitted={completedQuestions.includes(currentQuestionNumber)}
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
            {isFaceDetected ? 'Live Session' : 'Sensor Alert'}
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
