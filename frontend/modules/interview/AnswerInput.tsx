import React, { useState, useEffect } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Mic, MicOff, Loader2, Send, ShieldAlert } from 'lucide-react';

interface AnswerInputProps {
    onSubmit: (answer: string) => void;
    onPrev?: () => void;
    onNext?: () => void;
    disabled: boolean;
    isEvaluating?: boolean;
    interviewId?: string;
    isListening?: boolean;
    isTranscribing?: boolean;
    onStartRecording?: (callback: (text: string) => void) => void;
    onStopRecording?: () => void;
    isStuck?: boolean;
    onRetry?: () => void;
    options?: string[];
    initialValue?: string | null;
}

export default function AnswerInput({
    onSubmit,
    onPrev,
    onNext,
    disabled,
    isEvaluating = false,
    interviewId,
    isListening = false,
    isTranscribing = false,
    onStartRecording,
    onStopRecording,
    isStuck = false,
    onRetry,
    options = [],
    initialValue = '',
}: AnswerInputProps) {
    const [text, setText] = useState('');
    const [selectedOption, setSelectedOption] = useState<number | null>(null);

    // Sync initial value when question changes
    useEffect(() => {
        if (options.length > 0 && initialValue) {
            const index = initialValue.charCodeAt(0) - 65;
            if (index >= 0 && index < options.length) {
                setSelectedOption(index);
                setText('');
            } else {
                setSelectedOption(null);
                setText(initialValue || '');
            }
        } else {
            setSelectedOption(null);
            setText(initialValue || '');
        }
    }, [initialValue]); // Only update when initialValue changes, avoiding resets on options re-render

    const handleTranscriptionResult = (transcribedText: string) => {
        setText((prev) => {
            const trimmedPrev = prev.trim();
            return trimmedPrev ? `${trimmedPrev} ${transcribedText}` : transcribedText;
        });
    };

    const handleMicClick = (e: React.MouseEvent) => {
        e.preventDefault();
        if (isListening) {
            onStopRecording?.();
        } else {
            onStartRecording?.(handleTranscriptionResult);
        }
    };

    const handleSubmit = (e?: React.FormEvent) => {
        e?.preventDefault();
        if (isListening) onStopRecording?.();
        
        const finalAnswer = options.length > 0 && selectedOption !== null 
            ? String.fromCharCode(65 + selectedOption)
            : text.trim();

        if (finalAnswer && !disabled) {
            onSubmit(finalAnswer);
            setText('');
            setSelectedOption(null);
        }
    };

    const isMCQ = options && options.length > 0;

    return (
        <Card className="w-full shadow-sm border border-slate-200 bg-white rounded-2xl lg:rounded-3xl overflow-hidden">
            <CardContent className="p-4 sm:p-6 lg:p-10">
                <form onSubmit={handleSubmit} className="flex flex-col space-y-4 lg:space-y-8">
                    {isMCQ ? (
                        <div className="space-y-4 lg:space-y-6">
                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest px-1">Select One Option</span>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 lg:gap-4">
                                {options.map((opt, i) => (
                                    <button
                                        key={i}
                                        type="button"
                                        onClick={() => setSelectedOption(i)}
                                        className={`p-4 lg:p-6 rounded-xl lg:rounded-2xl border-2 text-left transition-all flex items-center gap-3 lg:gap-4 group ${selectedOption === i ? 'bg-blue-50 border-blue-600 shadow-lg shadow-blue-100' : 'bg-slate-50 border-transparent hover:border-slate-200 hover:bg-white'}`}
                                    >
                                        <div className={`w-8 h-8 lg:w-10 lg:h-10 rounded-lg lg:rounded-xl flex items-center justify-center font-black text-xs lg:text-sm transition-colors ${selectedOption === i ? 'bg-blue-600 text-white' : 'bg-white border-2 border-slate-100 text-slate-400 group-hover:border-blue-200 group-hover:text-blue-500'}`}>
                                            {String.fromCharCode(65 + i)}
                                        </div>
                                        <span className={`text-sm lg:text-lg font-bold ${selectedOption === i ? 'text-blue-900' : 'text-slate-600'}`}>{opt}</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-4 lg:space-y-6">
                             <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest px-1">Detailed Response</span>
                             <Textarea
                                placeholder={isEvaluating ? "The board is reviewing your response..." : "Provide your response here, or use the microphone to speak..."}
                                className="min-h-[120px] lg:min-h-[180px] resize-y text-sm lg:text-lg p-4 lg:p-8 bg-slate-50 focus:bg-white transition-all rounded-2xl lg:rounded-3xl border-slate-200 focus:ring-2 focus:ring-primary/20"
                                value={text}
                                onChange={(e) => setText(e.target.value)}
                                disabled={disabled || isEvaluating}
                            />
                        </div>
                    )}
                    
                    <div className="flex flex-col sm:flex-row justify-between items-center gap-4 pt-2 lg:pt-4">
                        <div className="flex items-center gap-4 lg:gap-6 w-full sm:w-auto">
                            <button 
                                type="button" 
                                onClick={onPrev}
                                className="flex items-center gap-2 text-slate-400 hover:text-slate-600 transition-colors disabled:opacity-30"
                                disabled={!onPrev}
                            >
                                <span className="text-[10px] lg:text-xs font-black uppercase tracking-widest">{'<'} Prev</span>
                            </button>
                            <button 
                                type="button" 
                                onClick={onNext}
                                className="flex items-center gap-2 text-slate-400 hover:text-slate-600 transition-colors disabled:opacity-30"
                                disabled={!onNext}
                            >
                                <span className="text-[10px] lg:text-xs font-black uppercase tracking-widest">Next {'>'}</span>
                            </button>
                            <span className="text-[9px] lg:text-[10px] text-slate-400 font-medium italic hidden xs:block">Answer each question and submit to move forward</span>
                        </div>

                        <div className="flex items-center gap-2 lg:gap-4 w-full sm:w-auto">
                            <Button variant="ghost" className="flex-1 sm:flex-none h-10 lg:h-14 px-4 lg:px-8 rounded-xl lg:rounded-2xl bg-slate-100 text-red-500 font-black text-[10px] lg:text-xs uppercase tracking-widest hover:bg-red-50">
                                End Early
                            </Button>
                            
                            {!isMCQ && (
                                <Button 
                                    type="button" 
                                    variant={isListening ? "destructive" : "outline"}
                                    size="icon" 
                                    disabled={disabled || isTranscribing} 
                                    onClick={handleMicClick}
                                    className={`w-10 h-10 lg:w-14 lg:h-14 rounded-xl lg:rounded-2xl shadow-sm transition-all ${isListening ? "animate-pulse shadow-lg shadow-red-500/20" : "hover:border-primary hover:text-primary"}`}
                                >
                                    {isTranscribing ? <Loader2 className="w-4 h-4 lg:w-5 lg:h-5 animate-spin" /> : isListening ? <MicOff className="w-4 h-4 lg:w-5 lg:h-5" /> : <Mic className="w-4 h-4 lg:w-5 lg:h-5" />}
                                </Button>
                            )}

                            <Button 
                                type="submit" 
                                disabled={disabled || (!text.trim() && selectedOption === null && !isListening)} 
                                className={`flex-[2] sm:flex-none h-10 lg:h-14 px-6 lg:px-10 rounded-xl lg:rounded-2xl shadow-lg font-black text-[10px] lg:text-sm uppercase tracking-widest transition-all ${selectedOption !== null || text.trim() ? 'bg-blue-600 hover:bg-blue-700 shadow-blue-200' : 'bg-slate-200 text-slate-400'}`}
                            >
                                Submit <span className="hidden xs:inline">Answer</span> <Send className="w-3 h-3 lg:w-4 lg:h-4 ml-1 lg:ml-2" />
                            </Button>
                        </div>
                    </div>
                </form>
            </CardContent>
        </Card>
    );
}
