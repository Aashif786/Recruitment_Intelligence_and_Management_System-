'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Camera, Mic, CheckCircle2, AlertCircle, Video, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';

interface InterviewHardwareCheckProps {
  onVerified: () => void;
}

export default function InterviewHardwareCheck({ onVerified }: InterviewHardwareCheckProps) {
  const [hasCamera, setHasCamera] = useState<boolean | null>(null);
  const [hasMic, setHasMic] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);

  const checkDevices = async () => {
    setChecking(true);
    try {
      // Request both at once
      const newStream = await navigator.mediaDevices.getUserMedia({ 
        video: true, 
        audio: true 
      });
      
      setStream(newStream);
      if (videoRef.current) {
        videoRef.current.srcObject = newStream;
      }

      const videoTrack = newStream.getVideoTracks()[0];
      const audioTrack = newStream.getAudioTracks()[0];

      setHasCamera(!!videoTrack && videoTrack.readyState === 'live');
      setHasMic(!!audioTrack && audioTrack.readyState === 'live');
      
      toast.success("Hardware verified successfully!");
    } catch (err: any) {
      console.error("Hardware check failed:", err);
      
      // Try to identify which one failed
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        toast.error("Camera or Microphone permission was denied.");
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        toast.error("Camera or Microphone not found on this device.");
      } else {
        toast.error("Failed to access hardware. Please check your settings.");
      }
      
      // If one is missing, try them separately to pinpoint
      try {
        const vStream = await navigator.mediaDevices.getUserMedia({ video: true });
        setHasCamera(true);
        vStream.getTracks().forEach(t => t.stop());
      } catch { setHasCamera(false); }

      try {
        const aStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setHasMic(true);
        aStream.getTracks().forEach(t => t.stop());
      } catch { setHasMic(false); }
    } finally {
      setChecking(false);
    }
  };

  // Initial check
  useEffect(() => {
    checkDevices();
    return () => {
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  const handleStart = () => {
    if (hasCamera && hasMic) {
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
      onVerified();
    } else {
      toast.error("You must grant access to both Camera and Microphone to proceed.");
    }
  };

  return (
    <div className="flex flex-col items-center justify-center py-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <Card className="max-w-2xl w-full bg-white shadow-2xl border-slate-200 overflow-hidden rounded-3xl">
        <CardHeader className="bg-slate-50 border-b p-8">
          <CardTitle className="text-3xl font-black text-slate-900 tracking-tight flex items-center gap-3">
            <ShieldAlert className="h-8 w-8 text-primary" />
            Hardware Verification
          </CardTitle>
          <CardDescription className="text-lg font-medium text-slate-600 mt-2">
            Professional AI interviews require active camera and microphone participation.
          </CardDescription>
        </CardHeader>

        <CardContent className="p-8 space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {/* Left: Camera Preview */}
            <div className="space-y-4">
              <div className="relative aspect-video bg-slate-900 rounded-2xl overflow-hidden shadow-inner border-2 border-slate-100 flex items-center justify-center group">
                {hasCamera ? (
                  <video 
                    ref={videoRef} 
                    autoPlay 
                    muted 
                    playsInline 
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="flex flex-col items-center gap-3 text-slate-500">
                    <Video className="h-12 w-12 opacity-20" />
                    <span className="text-xs font-bold uppercase tracking-widest opacity-40">Camera Disabled</span>
                  </div>
                )}
                <div className="absolute top-4 left-4">
                    <div className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-tighter flex items-center gap-1.5 backdrop-blur-md ${hasCamera ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-red-500/20 text-red-400 border border-red-500/30'}`}>
                        <div className={`h-1.5 w-1.5 rounded-full ${hasCamera ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
                        Camera: {hasCamera ? 'Live' : 'Inactive'}
                    </div>
                </div>
              </div>
            </div>

            {/* Right: Status Checklist */}
            <div className="space-y-6">
              <div className="space-y-4">
                <div className={`p-4 rounded-2xl border transition-all ${hasCamera ? 'bg-green-50 border-green-100' : 'bg-slate-50 border-slate-100'}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-xl ${hasCamera ? 'bg-green-500 text-white' : 'bg-slate-200 text-slate-400'}`}>
                        <Camera className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="font-bold text-slate-900">Camera Access</div>
                        <div className="text-xs text-slate-500 font-medium">Verify visual identity</div>
                      </div>
                    </div>
                    {hasCamera ? <CheckCircle2 className="h-6 w-6 text-green-500" /> : <AlertCircle className="h-6 w-6 text-red-400" />}
                  </div>
                </div>

                <div className={`p-4 rounded-2xl border transition-all ${hasMic ? 'bg-green-50 border-green-100' : 'bg-slate-50 border-slate-100'}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-xl ${hasMic ? 'bg-green-500 text-white' : 'bg-slate-200 text-slate-400'}`}>
                        <Mic className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="font-bold text-slate-900">Microphone Access</div>
                        <div className="text-xs text-slate-500 font-medium">Verify voice responses</div>
                      </div>
                    </div>
                    {hasMic ? <CheckCircle2 className="h-6 w-6 text-green-500" /> : <AlertCircle className="h-6 w-6 text-red-400" />}
                  </div>
                </div>
              </div>

              <div className="p-4 bg-amber-50 rounded-2xl border border-amber-100">
                <div className="flex gap-3">
                  <AlertCircle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                  <p className="text-xs font-semibold text-amber-700 leading-relaxed">
                    Make sure you are in a well-lit environment and using a quiet space for clear voice recognition.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </CardContent>

        <CardFooter className="bg-slate-50 border-t p-8 flex flex-col sm:flex-row gap-4">
          <Button 
            variant="outline" 
            onClick={checkDevices} 
            disabled={checking}
            className="h-14 px-8 rounded-2xl font-bold text-slate-600 border-2 border-slate-200 hover:bg-slate-100 flex-1 sm:flex-none"
          >
            Re-check Hardware
          </Button>
          <Button 
            onClick={handleStart} 
            disabled={!hasCamera || !hasMic || checking}
            className={`h-14 px-12 rounded-2xl font-black text-lg flex-1 shadow-xl transition-all active:scale-95 ${(!hasCamera || !hasMic) ? 'opacity-50 grayscale cursor-not-allowed' : 'bg-primary hover:bg-primary/90 shadow-primary/25 shadow-lg'}`}
          >
            Start Interview
          </Button>
        </CardFooter>
      </Card>
      
      <p className="mt-8 text-sm text-slate-400 font-medium max-w-lg text-center leading-relaxed">
        By proceeding, you agree to being recorded for evaluation purposes. Ensure your internet connection is stable.
      </p>
    </div>
  );
}


