import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CheckCircle2, Circle, HelpCircle, XCircle } from 'lucide-react';

interface SidebarSectionProps {
    title: string;
    count: number;
    current: number;
    startIndex: number;
    completed: number[];
    incorrect: number[];
    onSelect: (index: number) => void;
    isLocked: boolean;
}

const SidebarSection = ({ title, count, current, startIndex, completed, incorrect, onSelect, isLocked }: SidebarSectionProps) => {
    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center px-1">
                <h3 className="text-sm font-black text-slate-800 uppercase tracking-widest">{title}</h3>
                <span className="text-[10px] font-bold text-slate-400">{completed.length}/{count}</span>
            </div>
            <div className="grid grid-cols-5 gap-2">
                {Array.from({ length: count }).map((_, i) => {
                    const globalIndex = startIndex + i;
                    const isCompleted = completed.includes(globalIndex);
                    const isIncorrect = incorrect.includes(globalIndex);
                    const isCurrent = current === globalIndex;

                    let bgColor = "bg-white border-slate-200 text-slate-400";
                    if (isLocked) {
                        bgColor = "bg-slate-50 border-slate-100 text-slate-300 opacity-40 cursor-not-allowed";
                    } else if (isCurrent) {
                        bgColor = "bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-200";
                    } else if (isIncorrect) {
                        bgColor = "bg-red-500 border-red-500 text-white";
                    } else if (isCompleted) {
                        bgColor = "bg-green-500 border-green-500 text-white";
                    }

                    return (
                        <button
                            key={i}
                            disabled={isLocked}
                            onClick={() => !isLocked && onSelect(globalIndex)}
                            className={`w-8 h-8 rounded-full border text-[10px] font-black flex items-center justify-center transition-all ${isLocked ? '' : 'hover:scale-110 active:scale-95'} ${bgColor}`}
                        >
                            {i + 1}
                        </button>
                    );
                })}
            </div>
        </div>
    );
};

interface InterviewSidebarProps {
    currentQuestion: number;
    completedQuestions: number[];
    incorrectQuestions: number[];
    onSelectQuestion: (index: number) => void;
    strikes: number;
    allQuestions: any[];
}

export default function InterviewSidebar({ 
    currentQuestion, 
    completedQuestions, 
    incorrectQuestions, 
    onSelectQuestion,
    strikes,
    allQuestions = []
}: InterviewSidebarProps) {

    // Group questions by type
    const groupedQuestions = React.useMemo(() => {
        const groups: Record<string, any[]> = {};
        allQuestions.forEach((q) => {
            const type = q.question_type || 'General';
            if (!groups[type]) groups[type] = [];
            groups[type].push(q);
        });
        return groups;
    }, [allQuestions]);

    const orderedTypes = ['aptitude', 'technical', 'behavioral'];
    const otherTypes = React.useMemo(() => {
        return Object.keys(groupedQuestions).filter(t => !orderedTypes.includes(t.toLowerCase()));
    }, [groupedQuestions]);
    
    const displayOrder = React.useMemo(() => {
        return [...orderedTypes, ...otherTypes];
    }, [otherTypes]);

    const lockedSections = React.useMemo(() => {
        const locked: Record<string, boolean> = {};
        
        let foundIncomplete = false;
        displayOrder.forEach((type) => {
            locked[type.toLowerCase()] = foundIncomplete;
            
            const group = groupedQuestions[type] || groupedQuestions[type.charAt(0).toUpperCase() + type.slice(1)];
            if (group && group.length > 0) {
                const hasIncomplete = group.some(q => !completedQuestions.includes(q.question_number));
                if (hasIncomplete) {
                    foundIncomplete = true;
                }
            }
        });
        
        return locked;
    }, [groupedQuestions, completedQuestions, displayOrder]);

    return (
        <div className="space-y-8 p-6 bg-white border-r border-slate-100 h-full overflow-y-auto no-scrollbar">
            {/* Security Status Card */}
            <div className="p-4 bg-slate-900 rounded-2xl space-y-3">
                <div className="flex items-center justify-between">
                    <span className="text-[9px] font-black text-slate-400 uppercase tracking-tighter">Security Monitor</span>
                    <div className="flex gap-1">
                        {[1, 2, 3].map(s => (
                            <div key={s} className={`w-2 h-2 rounded-full ${strikes >= s ? 'bg-red-500 animate-pulse' : 'bg-slate-700'}`} />
                        ))}
                    </div>
                </div>
                <p className="text-[9px] font-medium text-slate-500 leading-tight">
                    {strikes === 0 ? "No violations detected. Session secure." : strikes === 1 ? "1 violation recorded. Please stay focused." : "Critical alert: One strike remaining."}
                </p>
            </div>

            {displayOrder.map(type => {
                const group = groupedQuestions[type] || groupedQuestions[type.charAt(0).toUpperCase() + type.slice(1)];
                if (!group || group.length === 0) return null;
                
                const startIndex = group[0].question_number;
                const isSectionLocked = lockedSections[type.toLowerCase()] || false;
                
                return (
                    <SidebarSection 
                        key={type}
                        title={type.charAt(0).toUpperCase() + type.slice(1)} 
                        count={group.length} 
                        current={currentQuestion} 
                        startIndex={startIndex}
                        completed={completedQuestions.filter(q => q >= startIndex && q < startIndex + group.length)}
                        incorrect={incorrectQuestions.filter(q => q >= startIndex && q < startIndex + group.length)}
                        onSelect={onSelectQuestion}
                        isLocked={isSectionLocked}
                    />
                );
            })}

            <div className="pt-8 border-t border-slate-50">
                <button className="w-full py-3 px-4 bg-slate-50 border border-slate-100 rounded-2xl text-[10px] font-black text-slate-500 uppercase tracking-widest hover:bg-slate-100 transition-colors">
                    Report an Issue
                </button>
            </div>
        </div>
    );
}
