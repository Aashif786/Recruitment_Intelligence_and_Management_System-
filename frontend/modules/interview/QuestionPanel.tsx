import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, BrainCircuit } from 'lucide-react';

interface QuestionPanelProps {
    question: { question: string, difficulty: string } | null;
    isLoading: boolean;
    currentQuestionNumber: number;
}

export default function QuestionPanel({ question, isLoading, currentQuestionNumber }: QuestionPanelProps) {

    const getDifficultyColor = (diff: string) => {
        switch (diff) {
            case 'easy': return 'bg-green-100 text-green-800 border-green-200';
            case 'medium': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
            case 'hard': return 'bg-red-100 text-red-800 border-red-200';
            default: return 'bg-gray-100 text-gray-800';
        }
    };

    return (
        <Card className="w-full border shadow-sm transition-all duration-300 min-h-[250px] relative overflow-hidden rounded-3xl bg-white">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary to-purple-500"></div>

            <CardHeader className="pb-3 px-10 pt-10">
                <div className="flex justify-between items-start">
                    <div className="space-y-2">
                        <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-blue-600 animate-pulse" />
                            <span className="text-[10px] font-black text-blue-600 uppercase tracking-widest">Current Question</span>
                        </div>
                        <CardTitle className="text-3xl font-black text-slate-900 tracking-tight flex items-baseline gap-3">
                            <span className="text-blue-600">Question {currentQuestionNumber}</span>
                        </CardTitle>
                    </div>
                    {question && (
                        <div className="px-6 py-2 rounded-full bg-purple-50 border border-purple-100 shadow-sm">
                            <span className="text-[10px] font-black text-purple-600 uppercase tracking-[0.2em]">
                                {question.difficulty.toUpperCase()} ROUND
                            </span>
                        </div>
                    )}
                </div>
            </CardHeader>

            <CardContent className="px-8 pb-8 pt-4 flex flex-col justify-center min-h-[150px]">
                {isLoading ? (
                    <div className="flex flex-col items-center justify-center space-y-4 opacity-60">
                        <Loader2 className="w-8 h-8 animate-spin text-primary" />
                        <p className="text-sm font-black text-slate-400 uppercase tracking-widest animate-pulse">Analyzing context for next question...</p>
                    </div>
                ) : (
                    <p className="text-xl md:text-2xl font-bold text-slate-800 leading-relaxed italic pr-4">
                        "{question?.question || "Initializing Assessment..."}"
                    </p>
                )}
            </CardContent>
        </Card>
    );
}
