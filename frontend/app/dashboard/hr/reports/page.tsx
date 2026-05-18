'use client'

import React, { useState, useMemo } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Slider } from "@/components/ui/slider"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { useSearchParams } from 'next/navigation'

// MUI Imports for Date Pickers
import dayjs, { Dayjs } from 'dayjs'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs'
import { DateCalendar } from '@mui/x-date-pickers/DateCalendar'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import { PickerDay } from '@mui/x-date-pickers'
import type { PickerDayProps } from '@mui/x-date-pickers'
import { Box } from '@mui/material'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import useSWR, { mutate } from 'swr'
import { fetcher } from '@/app/dashboard/lib/swr-fetcher'
import { API_BASE_URL } from '@/lib/config'
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer
} from 'recharts'
import { Download, FileText, Filter, Search, AlertCircle, CheckCircle2, XCircle, RotateCcw, Activity, Video, CameraOff, BarChart, ChevronLeft, ChevronRight } from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { cn } from '@/app/dashboard/lib/utils'

import { StatusChart, DetailedMetricsChart, SkillProficiencyChart } from '@/components/reports/Charts'
import { MetricCard } from '@/components/reports/MetricCard'
import { ReportCard } from '@/components/reports/ReportCard'
import { CategoryScoreCard } from '@/components/reports/CategoryScoreCard'
import {
  isAnswerEmpty,
  getDisplayedQuestionScore,
  isInterviewNotCompleted,
  isProgressionAllZeros,
  isRadarAllZeros,
} from '@/components/reports/interviewIncomplete'

// Constants
const SKILL_CATEGORIES = [
  "backend", "business_analyst", "business_intelligence", "CAE-MECHANICAL",
  "customer_support", "cybersecurity", "data_analysis", "database_admin",
  "devops", "digital_marketing", "electrical", "embedded_systems",
  "finance_accounting", "frontend", "fullstack", "generative_ai",
  "graphic_design", "healthcare_it", "hr", "instrumentation", "legal",
  "mobile", "networking", "project_management", "qa_testing", "sales_crm",
  "Steel_detailing", "ui_ux", "video_editing"
]

// Types
interface Evaluation {
  overall?: number
  relevance?: number
  action_impact?: number
  communication?: number
  coherence?: number
  empathy?: number
  situational_handling?: number
  self_awareness?: number
  technical_accuracy?: number
  completeness?: number
  clarity?: number
  depth?: number
  practicality?: number
  strengths?: string[]
  weaknesses?: string[]
}

interface QuestionEvaluation {
  question: string
  answer: string
  evaluation: Evaluation
  question_number?: number
  question_type?: 'technical' | 'behavioral' | 'aptitude'
  correct?: boolean
  score?: number
}

interface CandidateProfile {
  candidate_name?: string
  candidate_email?: string
  applied_role?: string
  experience_level?: string
  primary_skill?: string
  confidence?: string
  communication?: string
  skills?: string[]
}

interface Report {
  id: string | number
  filename: string
  timestamp: string
  display_date: string
  display_date_short: string
  status: string
  status_color: string
  overall_score: number
  final_score: number
  total_questions_answered: number
  question_evaluations: QuestionEvaluation[]
  candidate_profile: CandidateProfile
  tech_score?: number
  comm_score?: number
  evaluated_skills?: string | null
  aptitude_score?: number | null
  behavioral_score?: number | null
  technical_score?: number | null
  first_level_score?: number | null
  aptitude_question_evaluations?: QuestionEvaluation[]
  aptitude_questions_answered?: number
  video_url?: string | null
  termination_reason?: string | null
}

// Helper to clean question text that may be stored as JSON array strings
function cleanQuestionText(text: string): string {
  if (!text) return '';
  let cleaned = text.trim();
  // Strip JSON array brackets: ["question text"] → question text
  if (cleaned.startsWith('[') && cleaned.endsWith(']')) {
    try {
      const parsed = JSON.parse(cleaned);
      if (Array.isArray(parsed) && parsed.length > 0) {
        cleaned = parsed[0];
      }
    } catch {
      // Not valid JSON array, try manual strip
      cleaned = cleaned.slice(1, -1).trim();
    }
  }
  // Strip surrounding quotes
  if ((cleaned.startsWith('"') && cleaned.endsWith('"')) ||
    (cleaned.startsWith("'") && cleaned.endsWith("'"))) {
    cleaned = cleaned.slice(1, -1);
  }
  return cleaned.trim();
}

function getRecommendationLabel(score: number) {
  if (score > 6) return 'Select';
  if (score > 4) return 'Consider';
  return 'Reject';
}

function getRecommendationColor(score: number) {
  if (score > 6) return 'bg-primary/10 text-primary border-primary/20';
  if (score > 4) return 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20';
  return 'bg-destructive/10 text-destructive border-destructive/20';
}

export default function ReportsPage() {

  const searchParams = useSearchParams()
  const urlReportId = searchParams.get('reportId')
  const urlSearch = searchParams.get('search')

  // Pagination & Filter State
  const [reportsPage, setReportsPage] = useState(1);
  const [reportsPerPage, setReportsPerPage] = useState(10);
  const [activeTab, setActiveTab] = useState('detailed');
  const [statusFilter, setStatusFilter] = useState('Default')
  const [jobFilter, setJobFilter] = useState('All')

  const [skillFilter, setSkillFilter] = useState('All')
  const [experienceFilter, setExperienceFilter] = useState('All')
  const [dateFilter, setDateFilter] = useState<Date | undefined>(undefined)

  const [scoreRange, setScoreRange] = useState([0, 10])
  const [pendingScoreRange, setPendingScoreRange] = useState([0, 10])
  const [searchQuery, setSearchQuery] = useState(urlSearch || '')
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState(searchQuery)

  // Debounce search query
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery);
    }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const [fromDate, setFromDate] = useState<Dayjs | null>(null)
  const [toDate, setToDate] = useState<Dayjs | null>(null)

  // Applied state for manual triggering
  const [appliedFilters, setAppliedFilters] = useState({
    search: '',
    status: 'Default',
    job: 'All',
    skill: 'All',
    experience: 'All',
    score: [0, 10],
    from: null as Dayjs | null,
    to: null as Dayjs | null,
    date: undefined as Date | undefined
  })



  // Construct API URL with server-side filters
  const reportsApiUrl = useMemo(() => {
    const q = new URLSearchParams();
    q.set("limit", String(reportsPerPage));
    q.set("skip", String((reportsPage - 1) * reportsPerPage));
    
    if (appliedFilters.status !== "Default") q.set("status", appliedFilters.status);
    if (appliedFilters.job !== "All") q.set("job_id", appliedFilters.job);
    if (appliedFilters.skill !== "All") q.set("skill", appliedFilters.skill);
    if (appliedFilters.experience !== "All") q.set("experience", appliedFilters.experience);
    if (appliedFilters.search) q.set("search", appliedFilters.search);
    if (appliedFilters.score[0] > 0) q.set("score_min", String(appliedFilters.score[0]));
    if (appliedFilters.score[1] < 10) q.set("score_max", String(appliedFilters.score[1]));
    
    const { from, to, date } = appliedFilters
    const hasValidRange = from && to ? !from.isAfter(to, 'day') : true
    
    if (from && hasValidRange) q.set("from_date", from.format('YYYY-MM-DD'));
    if (to && hasValidRange) q.set("to_date", to.format('YYYY-MM-DD'));

    if (date && !from && !to) {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const d = `${year}-${month}-${day}`;
      q.set("from_date", d);
      q.set("to_date", d);
    }

    return `/api/analytics/reports?${q.toString()}`;
  }, [reportsPage, reportsPerPage, appliedFilters]);



  // Dedicated Heatmap Data (Unfiltered by date/score to keep heatmap consistent)
  const heatmapApiUrl = useMemo(() => {
    const q = new URLSearchParams();
    q.set("limit", "1000"); // Get a large enough sample for the heatmap
    return `/api/analytics/reports?${q.toString()}`;
  }, []);

  const { data: reportsResponse, error: fetchError, isLoading: isSWRDashboardLoading } = useSWR<{ reports: Report[], total: number, count: number, failed?: number, pages: number }>(reportsApiUrl, fetcher)
  const { data: heatmapResponse } = useSWR<any>(heatmapApiUrl, fetcher)

  const rawReports = Array.isArray(reportsResponse)
    ? reportsResponse
    : (reportsResponse?.reports || []);
  const heatmapReports = Array.isArray(heatmapResponse)
    ? heatmapResponse
    : (heatmapResponse?.reports || []);
  const totalCount = Array.isArray(reportsResponse)
    ? reportsResponse.length
    : (reportsResponse?.total ?? rawReports.length ?? 0);
  const totalPages = Array.isArray(reportsResponse)
    ? Math.ceil((reportsResponse.length || 0) / reportsPerPage)
    : (reportsResponse?.pages ?? Math.ceil(((reportsResponse?.total ?? 0) / reportsPerPage)));



  const reports = useMemo(() => {
    const processed = rawReports.map(report => {
      let techSum = 0, behSum = 0, commSum = 0;
      let techCount = 0, behCount = 0, commCount = 0;

      const allQ = [...(report?.question_evaluations || []), ...(report?.aptitude_question_evaluations || [])];

      allQ.forEach(q => {
        const score = q?.evaluation?.overall ?? q?.score ?? 0;
        const qType = (q?.question_type || "technical").toLowerCase();

        if (qType === 'behavioral') {
          behSum += score;
          behCount++;
        } else if (qType === 'technical') {
          techSum += score;
          techCount++;
        }

        if (q?.evaluation?.clarity !== undefined) {
          commSum += q.evaluation.clarity;
          commCount++;
        }
      });

      // Aptitude Calculation
      const aptQty = report?.aptitude_question_evaluations?.length || 0;
      const aptCorrect = report?.aptitude_question_evaluations?.filter((q: QuestionEvaluation) => q.correct).length || 0;
      const aptScore = aptQty > 0 ? (aptCorrect / aptQty) * 10 : report?.aptitude_score;

      return {
        ...report,
        tech_score: techCount > 0 ? techSum / techCount : report?.tech_score,
        behavioral_score: behCount > 0 ? behSum / behCount : report?.behavioral_score,
        aptitude_score: aptScore,
        comm_score: commCount > 0 ? commSum / commCount : report?.comm_score,
      };
    });

    // Developer Contract Validation Log
    if (process.env.NODE_ENV === 'development') {
      console.log(`[REPORTS] Pipeline: API(${rawReports.length}) -> Processed(${processed.length})`);
    }

    return processed;
  }, [rawReports])



  // Contract Validation Warning
  React.useEffect(() => {
    if (reportsResponse && !Array.isArray(reportsResponse) && !reportsResponse.reports) {
      console.warn("[REPORTS] API Contract Violation: Response missing 'reports' array.", reportsResponse);
    }
  }, [reportsResponse]);


  const getStatusColor = (status: string) => {
    switch (status) {
      case 'hired': return 'bg-primary/10 text-primary border-primary/20'
      case 'rejected': return 'bg-destructive/10 text-destructive border-destructive/20'
      case 'review_later': return 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
      case 'interview_scheduled':
      case 'approved_for_interview': return 'bg-accent/10 text-accent border-accent/20'
      case 'interview_completed': return 'bg-secondary/10 text-secondary border-secondary/20'
      default: return 'bg-muted text-muted-foreground border-border'
    }
  }

  const getStatusLabel = (status: string) => {
    return status?.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ') || status
  }

  // ONLY show the full page spinner on the very FIRST load when we have no data at all.
  // Subsequent re-fetches (filters) will show the existing data while loading in the background (SWR behavior).
  const isInitialLoading = isSWRDashboardLoading && !reportsResponse
  const [selectedQuestion, setSelectedQuestion] = useState<QuestionEvaluation | null>(null)
  const [viewingReport, setViewingReport] = useState<Report | null>(null)
  const [reportView, setReportView] = useState<'technical' | 'aptitude' | 'behavioral'>('technical');

  // Effect to auto-open report if reportId is in URL
  React.useEffect(() => {
    if (urlReportId && reports.length > 0) {
      const reportToView = reports.find(r =>
        String(r.id) === String(urlReportId) ||
        r.filename.includes(String(urlReportId))
      );
      if (reportToView) {
        setViewingReport(reportToView);
      }
    }
  }, [urlReportId, reports]);

  // Derived Data for Filters (Fetch from all reports for heatmap if needed, but for now we use what we have)
  const { data: allJobsData } = useSWR<any[]>('/api/jobs?limit=500', fetcher);
  const uniqueExperiences = useMemo(() => ["intern", "junior", "mid", "senior", "lead"], [])

  // Derived Interview Counts for Calendar Heatmap
  const interviewCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    heatmapReports.forEach((r: Report) => {
      const date = new Date(r.timestamp)
      if (!isNaN(date.getTime())) {
        const dateStr = date.toDateString()
        counts[dateStr] = (counts[dateStr] || 0) + 1
      }
    })
    return counts
  }, [heatmapReports])

  const ReportDensityDay = (props: PickerDayProps) => {
    const dayKey = props.day.toDate().toDateString()
    const count = interviewCounts[dayKey] || 0
    const intensity = count >= 5 ? 1 : count >= 3 ? 0.75 : count >= 1 ? 0.5 : 0
    return (
      <PickerDay
        {...props}
        sx={{
          ...(count > 0 && {
            boxShadow: `inset 0 -3px 0 0 hsl(var(--primary) / ${intensity})`,
            fontWeight: 600,
          }),
        }}
      />
    )
  }

  // Since filtering is now server-side, filteredReports is just reports
  const filteredReports = reports;

  // Metrics
  const metrics = useMemo(() => {
    const total = reportsResponse?.total || reports.length;
    let selectedCount = 0;
    let holdCount = 0;
    let rejectedCount = 0;
    let terminatedCount = 0;
    let incompleteCount = 0;

    filteredReports.forEach((r: Report) => {
      if (r.termination_reason) {
        terminatedCount++;
      } else if (isInterviewNotCompleted(r as any)) {
        incompleteCount++;
      } else {
        const label = getRecommendationLabel(Number(r?.overall_score || 0));
        if (label === 'Select') selectedCount++;
        else if (label === 'Consider') holdCount++;
        else rejectedCount++;
      }
    });

    const avgScore = total > 0 ? (filteredReports.reduce((acc: number, r: Report) => acc + Number(r?.overall_score || 0), 0) / (filteredReports.length || 1)).toFixed(2) : '0.00'
    const avgQuestions = total > 0 ? (filteredReports.reduce((acc: number, r: Report) => acc + (r?.total_questions_answered || 0), 0) / (filteredReports.length || 1)).toFixed(1) : '0.0'

    return { total, selected: selectedCount, hold: holdCount, rejected: rejectedCount, terminated: terminatedCount, incomplete: incompleteCount, avgScore, avgQuestions }
  }, [filteredReports, reportsResponse])

  const isAnyFilterActive = useMemo(() => {
    return (
      searchQuery !== '' ||
      statusFilter !== 'Default' ||
      jobFilter !== 'All' ||
      skillFilter !== 'All' ||
      experienceFilter !== 'All' ||
      (scoreRange[0] !== 0 || scoreRange[1] !== 10) ||
      fromDate !== null ||
      toDate !== null ||
      dateFilter !== undefined
    )
  }, [searchQuery, statusFilter, jobFilter, skillFilter, experienceFilter, scoreRange, fromDate, toDate, dateFilter])

  const isDirty = useMemo(() => {
    return (
      searchQuery !== appliedFilters.search ||
      statusFilter !== appliedFilters.status ||
      jobFilter !== appliedFilters.job ||
      skillFilter !== appliedFilters.skill ||
      experienceFilter !== appliedFilters.experience ||
      scoreRange[0] !== appliedFilters.score[0] ||
      scoreRange[1] !== appliedFilters.score[1] ||
      fromDate !== appliedFilters.from ||
      toDate !== appliedFilters.to ||
      dateFilter !== appliedFilters.date
    )
  }, [searchQuery, statusFilter, jobFilter, skillFilter, experienceFilter, scoreRange, fromDate, toDate, dateFilter, appliedFilters])

  const applyFilters = () => {
    setAppliedFilters({
      search: searchQuery,
      status: statusFilter,
      job: jobFilter,
      skill: skillFilter,
      experience: experienceFilter,
      score: scoreRange,
      from: fromDate,
      to: toDate,
      date: dateFilter
    })
    setReportsPage(1)
  }

  // Chart Data for Report Modal
  const radarData = useMemo(() => {
    if (!viewingReport) return [];
    let tech = 0, comm = 1, depthScore = 0, completenessScore = 0, practicalityScore = 0;
    let count = viewingReport.question_evaluations?.length || 1;

    viewingReport.question_evaluations?.forEach(q => {
      tech += q.evaluation?.technical_accuracy || 0;
      comm += q.evaluation?.clarity || 0;
      depthScore += q.evaluation?.depth || 0;
      completenessScore += q.evaluation?.completeness || 0;
      practicalityScore += q.evaluation?.practicality || 0;
    });

    return [
      { subject: 'Technical', A: tech / count, fullMark: 10 },
      { subject: 'Clarity', A: comm / count, fullMark: 10 },
      { subject: 'Depth', A: depthScore / count, fullMark: 10 },
      { subject: 'Completeness', A: completenessScore / count, fullMark: 10 },
      { subject: 'Practicality', A: practicalityScore / count, fullMark: 10 },
    ];
  }, [viewingReport]);

  const lineData = useMemo(() => {
    if (!viewingReport) return [];
    return viewingReport.question_evaluations?.map((q) => ({
      name: `Q${(q as any).question_number || '?'}`,
      Tech: q.evaluation?.technical_accuracy || 0,
      Comm: q.evaluation?.clarity || 0,
    })) || [];
  }, [viewingReport]);

  const interviewNotCompleted = useMemo(
    () => (viewingReport ? isInterviewNotCompleted(viewingReport) : false),
    [viewingReport]
  );

  const progressionShowsPlaceholder = interviewNotCompleted || isProgressionAllZeros(lineData);
  const radarShowsPlaceholder = interviewNotCompleted || isRadarAllZeros(radarData);

  // Generate Text Report
  const generateTextReport = (report: Report) => {
    let text = `============================================================\n`
    text += `VIRTUAL HR INTERVIEWER - CANDIDATE REPORT\n`
    text += `============================================================\n\n`

    text += `Report Generated: ${report.display_date}\n`
    text += `Total Questions: ${report.total_questions_answered}\n`
    text += `Overall Score: ${report.overall_score.toFixed(2)}/10\n`
    text += `Status: ${report.status}\n\n`

    text += `CANDIDATE PROFILE\n`
    text += `----------------------------------------\n`
    text += `Name: ${report.candidate_profile.candidate_name || 'N/A'}\n`
    text += `Email: ${report.candidate_profile.candidate_email || 'N/A'}\n`
    text += `Role: ${report.candidate_profile.applied_role || 'N/A'}\n`
    text += `Experience: ${report.candidate_profile.experience_level || 'N/A'}\n`
    text += `Primary Skill: ${report.candidate_profile.primary_skill || 'N/A'}\n`
    text += `Communication: ${report.candidate_profile.communication || 'N/A'}\n\n`

    text += `QUESTION ANALYSIS\n`
    text += `----------------------------------------\n`
    report.question_evaluations.forEach((q, i) => {
      text += `\nQuestion ${i + 1}: ${q.question}\n`
      text += `Score: ${q.evaluation.overall}/10\n`
      if (q.evaluation.strengths) {
        text += `  Strengths:\n${q.evaluation.strengths.map(s => `    - ${s}`).join('\n')}\n`
      }
      if (q.evaluation.weaknesses) {
        text += `  Weaknesses:\n${q.evaluation.weaknesses.map(w => `    - ${w}`).join('\n')}\n`
      }
    })

    return text
  }

  const downloadCSV = () => {
    // Reorganized headers to put important metrics first, long skills list last
    const headers = ['Candidate,Date,Role,Score,Status,Experience,Skills']
    const rows = filteredReports.map((r: Report) => {
      // Clean up skills and handle commas/quotes for CSV safety
      let cleanSkills = 'N/A';
      try {
        const skillsData = r.candidate_profile.primary_skill || r.candidate_profile.skills;
        if (skillsData) {
          const skillsArray = typeof skillsData === 'string' ? JSON.parse(skillsData) : skillsData;
          cleanSkills = Array.isArray(skillsArray) ? skillsArray.join('; ') : String(skillsData);
        }
      } catch (e) {
        cleanSkills = String(r.candidate_profile.primary_skill || 'N/A');
      }

      // Format status for readability
      const status = r.status.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

      return [
        `"${r.candidate_profile.candidate_name || r.filename.replace('.json', '')}"`,
        `"${r.display_date_short}"`,
        `"${r.candidate_profile.applied_role || 'N/A'}"`,
        `"${r.overall_score.toFixed(2)}"`,
        `"${status}"`,
        `"${r.candidate_profile.experience_level || 'N/A'}"`,
        `"${cleanSkills.replace(/"/g, '""')}"` // Skills at the end
      ].join(',')
    })

    // Add UTF-8 BOM for better Excel compatibility
    const csvContent = '\uFEFF' + [headers, ...rows].join('\n')
    downloadFile(csvContent, `interview_reports_${new Date().toISOString().split('T')[0]}.csv`, 'csv')
  }

  const downloadFile = (content: string, filename: string, type: 'json' | 'txt' | 'csv') => {
    let mimeType = 'text/plain'
    if (type === 'json') mimeType = 'application/json'
    if (type === 'csv') mimeType = 'text/csv'

    const blob = new Blob([content], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const clearAllFilters = () => {
    setStatusFilter('Default')
    setJobFilter('All')
    setSkillFilter('All')
    setExperienceFilter('All')
    setScoreRange([0, 10])
    setPendingScoreRange([0, 10])
    setSearchQuery('')
    setDateFilter(undefined)
    setFromDate(null)
    setToDate(null)

    setAppliedFilters({
      search: '',
      status: 'Default',
      job: 'All',
      skill: 'All',
      experience: 'All',
      score: [0, 10],
      from: null,
      to: null,
      date: undefined
    })

    setReportsPage(1)
  }

  if (isInitialLoading) {
    return (
      <div className="flex justify-center items-center h-screen bg-background">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="p-8">
        <div className="bg-red-50 text-red-600 p-4 rounded-lg border border-red-200">
          <h3 className="font-bold">Error Loading Reports</h3>
          <p>{fetchError.message || 'An error occurred while fetching reports.'}</p>
          <Button onClick={() => mutate(reportsApiUrl)} variant="outline" className="mt-2">Retry</Button>
        </div>
      </div>
    )
  }

  return (
    /*
      Main Layout Container
      - Uses flex-col to stack Header and Grid.
      - On desktop (lg), sets explicit height [100vh - 9rem] to fill remaining space
        (allowing for 4rem header + 4rem layout padding + 1rem safety).
      - 'min-h-0' is crucial for allowing flex children to scroll.
    */
    <div className="w-full max-w-[1600px] mx-auto flex flex-col gap-4 lg:h-[calc(100vh-7.5rem)]">

      
      {/* Header - Fixed at the top of the component */}
      <PageHeader
        title="Interview Reports"
        description={`Analytics and detailed reports for ${totalCount} candidates`}
        icon={BarChart}
      />

      {/* Question Detail Modal */}
      <Dialog open={!!selectedQuestion} onOpenChange={(open) => !open && setSelectedQuestion(null)}>
        <DialogContent className="w-full md:!max-w-[35vw] md:!w-[35vw] max-h-[90vh] overflow-y-auto bg-background/95 p-6">
          <DialogHeader>
            <DialogTitle className="text-2xl font-bold">Detailed Question Analysis</DialogTitle>
            <DialogDescription>In-depth review of the candidate's response.</DialogDescription>
          </DialogHeader>

          {selectedQuestion && (
            <div className="space-y-8 mt-4">
              {/* Row 1: Question */}
              <div className="space-y-2">
                <h4 className="text-lg font-bold text-slate-900 dark:text-slate-50">Question:</h4>
                <p className="text-lg text-slate-900 dark:text-slate-50 bg-card p-6 rounded-xl border shadow-sm leading-relaxed">
                  {cleanQuestionText(selectedQuestion.question)}
                </p>
              </div>

              {/* Row 2: Answer */}
              <div className="space-y-2">
                <h4 className="text-lg font-bold text-slate-900 dark:text-slate-50">Answer:</h4>
                <p className={`text-base bg-card p-6 rounded-xl border shadow-sm leading-relaxed whitespace-pre-wrap ${isAnswerEmpty(selectedQuestion.answer) ? 'text-muted-foreground italic' : 'text-slate-900 dark:text-slate-50'}`}>
                  {isAnswerEmpty(selectedQuestion.answer) ? 'Candidate did not provide an answer.' : selectedQuestion.answer}
                </p>
              </div>

              {/* Row 3 & 4: Category Scores & Overall Score */}
              <div className="grid grid-cols-1 gap-8 items-center bg-card p-6 rounded-xl border shadow-sm">
                <div className="space-y-4">
                  <h4 className="text-sm font-bold text-muted-foreground uppercase tracking-wider mb-2">Evaluation Scores</h4>
                  {/* Evaluation Details */}
                  <div className={`grid grid-cols-2 ${selectedQuestion.question_type === 'behavioral' ? 'md:grid-cols-3' : 'md:grid-cols-5'} gap-4`}>
                    {(() => {
                      const na = isAnswerEmpty(selectedQuestion.answer)
                      const ev = selectedQuestion.evaluation ?? {}
                      return (selectedQuestion.question_type === 'behavioral') ? (
                        <>
                          <MetricCard title="Relevance" score={ev.relevance ?? ev.communication ?? ev.technical_accuracy ?? 0} notAvailable={na} />
                          <MetricCard title="Action & Impact" score={ev.action_impact ?? ev.situational_handling ?? ev.completeness ?? 0} notAvailable={na} />
                          <MetricCard title="Clarity" score={ev.clarity ?? ev.coherence ?? 0} notAvailable={na} />
                        </>
                      ) : (
                        <>
                          <MetricCard title="Technical Accuracy" score={ev.technical_accuracy ?? 0} notAvailable={na} />
                          <MetricCard title="Completeness" score={ev.completeness ?? 0} notAvailable={na} />
                          <MetricCard title="Clarity" score={ev.clarity ?? 0} notAvailable={na} />
                          <MetricCard title="Depth" score={ev.depth ?? 0} notAvailable={na} />
                          <MetricCard title="Practicality" score={ev.practicality ?? 0} notAvailable={na} />
                        </>
                      )
                    })()}
                  </div>
                </div>
              </div>


              {/* Row 5: Strengths | Areas for Improvement */}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Strengths */}
                <div>
                  <h4 className="text-lg font-bold text-slate-900 dark:text-slate-50 mb-3">Strengths:</h4>
                  <div className="bg-primary/10 border border-primary/20 rounded-xl p-6 h-full shadow-sm">
                    {selectedQuestion.evaluation.strengths && selectedQuestion.evaluation.strengths.length > 0 ? (
                      <ul className="space-y-3">
                        {selectedQuestion.evaluation.strengths.map((s, idx) => (
                          <li key={idx} className="flex gap-3 text-base text-primary leading-relaxed">
                            <CheckCircle2 className="h-5 w-5 shrink-0 mt-0.5 text-primary" />
                            <span>{s}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-muted-foreground italic text-sm">No specific strengths noted.</p>
                    )}
                  </div>
                </div>

                {/* Weaknesses */}
                <div>
                  <h4 className="text-lg font-bold text-slate-900 dark:text-slate-50 mb-3">Areas for Improvement:</h4>
                  <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-6 h-full shadow-sm">
                    {selectedQuestion.evaluation.weaknesses && selectedQuestion.evaluation.weaknesses.length > 0 ? (
                      <ul className="space-y-3">
                        {selectedQuestion.evaluation.weaknesses.map((w, idx) => (
                          <li key={idx} className="flex gap-3 text-base text-destructive leading-relaxed">
                            <XCircle className="h-5 w-5 shrink-0 mt-0.5 text-destructive" />
                            <span>{w}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-muted-foreground italic text-sm">No specific improvements noted.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/*
              Content Grid
              - 'flex-1 min-h-0' makes it take remaining height and ALLOWS shrinkage/scrolling.
              - On desktop (lg), it's a 4-column grid.
              - On mobile, it stacks naturally.
            */}
      <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4 items-start">


        {/*
                  LEFT COMPONENT (Filter Panel)
                  - On desktop: 'h-full flex flex-col' ensures it fills the grid column height.
                  - Filters themselves live in a scrollable CardContent.
                  - It stays "sticky"/fixed effectively because the container doesn't scroll,
                    only the content inside this Card (if needed) and the Right Component.
                */}
        <div className="lg:col-span-1 md:col-span-1 max-h-full lg:max-h-[calc(100vh-10rem)] animate-in fade-in slide-in-from-left-8 duration-700 ease-out fill-mode-both">

          <Card className="h-full flex flex-col shadow-sm border-border/60 !py-0 !gap-0 bg-card/80 backdrop-blur-sm">
            <CardHeader className="p-4 !pb-0 shrink-0 border-b border-border/50">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Filter className="h-4 w-4 text-primary" /> Filters
                </CardTitle>
                <div className="flex items-center gap-1.5 min-w-[40px] justify-end">
                  <TooltipProvider delayDuration={100}>
                    {/* Reset Button - Always shown when filters are active, slides left if dirty */}
                    {isAnyFilterActive && (
                      <div className="flex items-center animate-in slide-in-from-right-4 duration-300">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-full transition-all"
                              onClick={clearAllFilters}
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent className="text-[10px]">Clear all filters</TooltipContent>
                        </Tooltip>
                      </div>
                    )}

                    {/* Apply Button (Tick) - Appears when changes are made */}
                    {isDirty && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-emerald-500 hover:text-emerald-600 hover:bg-emerald-50 rounded-full animate-in zoom-in spin-in-90 duration-300 shadow-sm border border-emerald-100"
                            onClick={applyFilters}
                          >
                            <CheckCircle2 className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent className="text-[10px] font-bold">Click to apply filters</TooltipContent>
                      </Tooltip>
                    )}

                    {/* Initial Reset Button - Only shown when absolutely nothing is active to maintain position */}
                    {!isAnyFilterActive && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-slate-300 cursor-not-allowed opacity-50"
                        disabled
                      >
                        <RotateCcw className="h-4 w-4" />
                      </Button>
                    )}
                  </TooltipProvider>
                </div>
              </div>
            </CardHeader>
            <CardContent className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-thin scrollbar-thumb-gray-200 scrollbar-track-transparent">
              {/* Search */}
              <div className="grid w-full items-center gap-1.5">
                <Label htmlFor="search" className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">Search</Label>
                <div className="relative">
                  <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-500 dark:text-slate-400" />
                  <TooltipProvider delayDuration={150}>
                    <Tooltip open={searchQuery.length > 0 && debouncedSearchQuery !== searchQuery}>
                      <TooltipTrigger asChild>
                        <Input
                          id="search"
                          placeholder="Candidate Name"
                          className="pl-8"
                          value={searchQuery}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              applyFilters();
                            }
                          }}
                          onChange={(e) => {
                            setSearchQuery(e.target.value)
                          }}
                        />
                      </TooltipTrigger>
                      <TooltipContent side="bottom" align="start" className="text-xs">
                        Press Enter after typing
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              </div>

              <div className="rounded-xl border border-border/60 bg-muted/30 p-3 space-y-2">
                <Label htmlFor="job-filter" className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest">Filter by Job</Label>
                <Select value={jobFilter} onValueChange={setJobFilter}>
                  <SelectTrigger id="job-filter" className="w-full h-9 text-sm rounded-lg bg-background/50 border-border/40">
                    <SelectValue placeholder="All Jobs" />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    <SelectItem value="All">All Jobs</SelectItem>
                    {allJobsData?.map((job: any) => (
                      <SelectItem key={job.id} value={String(job.id)}>{job.title}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Grouped Status/Exp/Skill Filters */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {/* Status Filter */}
                <div className="space-y-1.5 p-2 rounded-xl border border-border/50 bg-muted/25">
                  <Label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Status</Label>
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger className="w-full h-9 text-xs rounded-lg bg-background/40 border-border/30">
                      <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent className="rounded-lg">
                      <SelectItem value="Default">Default</SelectItem>
                      <SelectItem value="Select">Selected</SelectItem>
                      <SelectItem value="Reject">Rejected</SelectItem>
                      <SelectItem value="Terminated">Terminated</SelectItem>
                      <SelectItem value="Not Completed">Incomplete</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Experience Filter */}
                <div className="space-y-1.5 p-2 rounded-xl border border-border/50 bg-muted/25">
                  <Label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Exp.</Label>
                  <Select value={experienceFilter} onValueChange={setExperienceFilter}>
                    <SelectTrigger className="w-full h-9 text-xs rounded-lg bg-background/40 border-border/30">
                      <SelectValue placeholder="Exp." />
                    </SelectTrigger>
                    <SelectContent className="rounded-lg">
                      <SelectItem value="All">All Levels</SelectItem>
                      {uniqueExperiences.map((exp, idx) => (
                        <SelectItem key={idx} value={exp}>{exp}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Skill Filter */}
                <div className="space-y-1.5 p-2 rounded-xl border border-border/50 bg-muted/25">
                  <Label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Skills</Label>
                  <Select value={skillFilter} onValueChange={setSkillFilter}>
                    <SelectTrigger className="w-full h-9 text-xs rounded-lg bg-background/40 border-border/30">
                      <SelectValue placeholder="Skills" />
                    </SelectTrigger>
                    <SelectContent className="rounded-lg max-h-[300px]">
                      <SelectItem value="All">All Skills</SelectItem>
                      {SKILL_CATEGORIES.map((skill, idx) => (
                        <SelectItem key={idx} value={skill}>
                          {skill.split(/[_-]/).map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()).join(' ')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>



              {/* Score Range */}
              <div className="space-y-1.5 p-3 rounded-xl border border-border/60 bg-muted/30">
                <div className="flex justify-between items-center">
                  <Label className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest">Score Range</Label>
                  <span className="text-[13px] font-sembold text-primary">{pendingScoreRange[0]} - {pendingScoreRange[1]}</span>
                </div>
                <Slider
                  defaultValue={[0, 10]}
                  max={10}
                  step={0.1}
                  value={pendingScoreRange}
                  onValueChange={setPendingScoreRange}
                  onValueCommit={setScoreRange}
                  className="py-2"
                />
              </div>


              <Separator className="my-1" />

              {/* Calendar */}
              <LocalizationProvider dateAdapter={AdapterDayjs}>
                <div className="space-y-3 p-3 rounded-xl border border-border/60 bg-muted/30">
                  <div className="space-y-2">
                    <Label className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest pb-1">Date Range</Label>
                    <div className="grid grid-cols-2 gap-1.5">
                      <DatePicker
                        label="From"
                        value={fromDate}
                        minDate={dayjs('1900-01-01')}
                        maxDate={toDate || dayjs()}
                        disableFuture
                        onChange={(newValue) => {
                          setFromDate(newValue)
                          if (toDate && newValue && newValue.isAfter(toDate, 'day')) {
                            setToDate(newValue)
                          }
                          if (dateFilter) setDateFilter(undefined)
                        }}
                        slotProps={{
                          textField: {
                            size: 'small',
                            fullWidth: true,
                            sx: {
                              '& .MuiInputBase-root': { 
                                fontSize: '0.875rem',
                                fontFamily: 'var(--font-sans) !important',
                              },
                              '& .MuiInputBase-input': {
                                color: 'hsl(var(--foreground)) !important',
                                WebkitTextFillColor: 'hsl(var(--foreground)) !important',
                              },
                              '& .MuiInputLabel-root': { 
                                color: 'hsl(var(--muted-foreground))' 
                              },
                              '& .MuiOutlinedInput-notchedOutline': { 
                                borderColor: 'hsl(var(--border) / 0.5)' 
                              },
                              '& .MuiSvgIcon-root': {
                                color: 'hsl(var(--muted-foreground))'
                              }
                            }
                          },
                          popper: {
                            sx: {
                              zIndex: 10000,
                            }
                          },
                          desktopPaper: {
                            sx: {
                              backgroundColor: 'hsl(var(--card)) !important',
                              backgroundImage: 'none !important',
                              opacity: '1 !important',
                              border: '1px solid hsl(var(--border))',
                              boxShadow: 'var(--shadow-xl)',
                              borderRadius: '12px',
                            }
                          }
                        }}
                      />
                      <DatePicker
                        label="To"
                        value={toDate}
                        minDate={fromDate || dayjs('1900-01-01')}
                        maxDate={dayjs()}
                        disableFuture
                        onChange={(newValue) => {
                          setToDate(newValue)
                          if (dateFilter) setDateFilter(undefined)
                        }}
                        slotProps={{
                          textField: {
                            size: 'small',
                            fullWidth: true,
                            sx: {
                              '& .MuiInputBase-root': { 
                                fontSize: '0.875rem',
                              },
                              '& .MuiInputBase-input': {
                                color: 'hsl(var(--foreground)) !important',
                                WebkitTextFillColor: 'hsl(var(--foreground)) !important',
                              },
                              '& .MuiInputLabel-root': { 
                                color: 'hsl(var(--muted-foreground))' 
                              },
                              '& .MuiOutlinedInput-notchedOutline': { 
                                borderColor: 'hsl(var(--border) / 0.5)' 
                              },
                              '& .MuiSvgIcon-root': {
                                color: 'hsl(var(--muted-foreground))'
                              }
                            }
                          },
                          popper: {
                            sx: {
                              zIndex: 10000,
                            }
                          },
                          desktopPaper: {
                            sx: {
                              backgroundColor: 'hsl(var(--card)) !important',
                              backgroundImage: 'none !important',
                              opacity: '1 !important',
                              border: '1px solid hsl(var(--border))',
                              boxShadow: 'var(--shadow-xl)',
                              borderRadius: '12px',
                            }
                          }
                        }}
                      />
                    </div>
                      <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                          setFromDate(null)
                          setToDate(null)
                          setDateFilter(undefined)
                      }}
                      className="h-7 text-xs text-muted-foreground hover:text-primary px-2 w-full mt-1 flex items-center gap-2"
                    >
                      <RotateCcw className="h-3 w-3" /> Reset to Default
                    </Button>
                  </div>

                  <Separator />

                  <div className="space-y-1">
                    <div className="flex justify-between items-center px-1">
                      <Label className="text-[12px] font-semibold text-muted-foreground uppercase tracking-wider">Select Date</Label>
                      {dateFilter && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDateFilter(undefined)}
                          className="h-5 text-[14px] text-muted-foreground hover:text-red-500 px-1"
                        >
                          Clear
                        </Button>
                      )}
                    </div>
                    <Box sx={{
                      position: 'relative',
                      zIndex: 1,
                      bgcolor: 'hsl(var(--muted) / 0.3)',
                      borderRadius: '12px',
                      border: '1px solid hsl(var(--border))',
                      overflow: 'hidden',
                      display: 'flex',
                      justifyContent: 'center',
                      fontFamily: 'var(--font-sans)',
                      '& *': { fontFamily: 'var(--font-sans) !important' },
                      '& .MuiDateCalendar-root': {
                        width: '100%',
                        height: 'auto',
                        maxWidth: '100%',
                        margin: '0',
                      },
                      '& .MuiPickersDay-root': {
                        width: '32px',
                        height: '32px',
                        fontSize: '0.8rem',
                        color: 'hsl(var(--foreground))',
                      },
                      '& .MuiTypography-root': {
                        fontSize: '0.8rem',
                        color: 'hsl(var(--foreground))',
                      },
                      '& .MuiSvgIcon-root': {
                        color: 'hsl(var(--foreground))',
                      },
                      '& .MuiPickersDay-root.Mui-selected': {
                        bgcolor: 'hsl(var(--primary)) !important',
                        color: 'hsl(var(--primary-foreground)) !important',
                      },
                      '& .MuiDayCalendar-weekDayLabel': {
                        color: 'hsl(var(--muted-foreground))',
                      }
                    }}>
                      <DateCalendar
                        value={dateFilter ? dayjs(dateFilter) : null}
                        maxDate={dayjs()}
                        disableFuture
                        onChange={(newValue) => {
                          setDateFilter(newValue?.toDate())
                          if (newValue) {
                            setFromDate(null)
                            setToDate(null)
                          }
                        }}
                        sx={{
                          backgroundColor: 'transparent',
                          '& .MuiPickersDay-root': {
                            color: 'hsl(var(--foreground))',
                          },
                          '& .MuiTypography-root': {
                            color: 'hsl(var(--foreground))'
                          },
                          '& .MuiSvgIcon-root': {
                            color: 'hsl(var(--foreground))'
                          }
                        }}
                        slots={{ day: ReportDensityDay }}
                      />
                    </Box>
                  </div>
                </div>
              </LocalizationProvider>
            </CardContent>
          </Card>
        </div>

        {/*
                  RIGHT COMPONENT (Reports & Metrics)
                  - On desktop: 'h-full overflow-y-auto' enables independent scrolling.
                  - The Main Layout/Body will NOT scroll; this div scrolls instead.
                  - Added padding-right/bottom for scrollbar comfort.
                */}
        <div className="lg:col-span-3 md:col-span-2 space-y-4">


          {/* Compact Metrics Strip */}
          <div className="animate-in fade-in slide-in-from-top-8 duration-700 ease-out fill-mode-both delay-100 rounded-xl border border-border/60 bg-card/80 backdrop-blur-sm px-3 py-2">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
              <div className="rounded-md bg-muted/40 px-3 py-2">
                <p className="text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">Total Reports</p>
                <p className="text-2xl font-bold leading-tight text-slate-900 dark:text-slate-100">{metrics.total}</p>
              </div>
              <div className="rounded-md bg-muted/40 px-3 py-2">
                <p className="text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">Avg Score</p>
                <p className="text-2xl font-bold leading-tight text-slate-900 dark:text-slate-100">{metrics.avgScore}</p>
              </div>
              <div className="rounded-md bg-muted/40 px-3 py-2">
                <p className="text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">Avg Questions</p>
                <p className="text-2xl font-bold leading-tight text-slate-900 dark:text-slate-100">{metrics.avgQuestions}</p>
              </div>
              <div className="rounded-md bg-muted/40 px-3 py-2">
                <p className="text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">Selection Rate</p>
                <p className="text-2xl font-bold leading-tight text-slate-900 dark:text-slate-100">{metrics.total > 0 ? Math.round((metrics.selected / metrics.total) * 100) : 0}%</p>
              </div>
            </div>
          </div>

          {/* Active Filters Summary */}
          {isAnyFilterActive && (
            <div className="flex flex-wrap gap-2 animate-in fade-in slide-in-from-top-4 duration-500">
              {appliedFilters.search && (
                <Badge variant="secondary" className="px-2 py-1 flex items-center gap-1 bg-primary/5 border-primary/20 text-primary">
                  Search: {appliedFilters.search}
                  <XCircle className="h-3 w-3 cursor-pointer hover:text-destructive" onClick={() => setSearchQuery('')} />
                </Badge>
              )}
              {appliedFilters.status !== 'Default' && (
                <Badge variant="secondary" className="px-2 py-1 flex items-center gap-1 bg-primary/5 border-primary/20 text-primary">
                  Status: {getStatusLabel(appliedFilters.status)}
                  <XCircle className="h-3 w-3 cursor-pointer hover:text-destructive" onClick={() => setStatusFilter('Default')} />
                </Badge>
              )}
              {appliedFilters.job !== 'All' && (
                <Badge variant="secondary" className="px-2 py-1 flex items-center gap-1 bg-primary/5 border-primary/20 text-primary">
                  Job: {allJobsData?.find((j: any) => String(j.id) === String(appliedFilters.job))?.title || 'Selected Job'}
                  <XCircle className="h-3 w-3 cursor-pointer hover:text-destructive" onClick={() => setJobFilter('All')} />
                </Badge>
              )}
              {appliedFilters.skill !== 'All' && (
                <Badge variant="secondary" className="px-2 py-1 flex items-center gap-1 bg-primary/5 border-primary/20 text-primary">
                  Skill: {appliedFilters.skill.split(/[_-]/).map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ')}
                  <XCircle className="h-3 w-3 cursor-pointer hover:text-destructive" onClick={() => setSkillFilter('All')} />
                </Badge>
              )}
              {appliedFilters.experience !== 'All' && (
                <Badge variant="secondary" className="px-2 py-1 flex items-center gap-1 bg-primary/5 border-primary/20 text-primary">
                  Exp: {appliedFilters.experience}
                  <XCircle className="h-3 w-3 cursor-pointer hover:text-destructive" onClick={() => setExperienceFilter('All')} />
                </Badge>
              )}
              {(appliedFilters.score[0] !== 0 || appliedFilters.score[1] !== 10) && (
                <Badge variant="secondary" className="px-2 py-1 flex items-center gap-1 bg-primary/5 border-primary/20 text-primary">
                  Score: {appliedFilters.score[0]} - {appliedFilters.score[1]}
                  <XCircle className="h-3 w-3 cursor-pointer hover:text-destructive" onClick={() => setScoreRange([0, 10])} />
                </Badge>
              )}
              {appliedFilters.from && (
                <Badge variant="secondary" className="px-2 py-1 flex items-center gap-1 bg-primary/5 border-primary/20 text-primary">
                  From: {appliedFilters.from.format('MMM D, YYYY')}
                  <XCircle className="h-3 w-3 cursor-pointer hover:text-destructive" onClick={() => setFromDate(null)} />
                </Badge>
              )}
              {appliedFilters.to && (
                <Badge variant="secondary" className="px-2 py-1 flex items-center gap-1 bg-primary/5 border-primary/20 text-primary">
                  To: {appliedFilters.to.format('MMM D, YYYY')}
                  <XCircle className="h-3 w-3 cursor-pointer hover:text-destructive" onClick={() => setToDate(null)} />
                </Badge>
              )}
              {appliedFilters.date && (
                <Badge variant="secondary" className="px-2 py-1 flex items-center gap-1 bg-primary/5 border-primary/20 text-primary">
                  On: {dayjs(appliedFilters.date).format('MMM D, YYYY')}
                  <XCircle className="h-3 w-3 cursor-pointer hover:text-destructive" onClick={() => setDateFilter(undefined)} />
                </Badge>
              )}
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => {
                  setSearchQuery('')
                  setStatusFilter('Default')
                  setJobFilter('All')
                  setSkillFilter('All')
                  setExperienceFilter('All')
                  setScoreRange([0, 10])
                  setFromDate(null)
                  setToDate(null)
                  setDateFilter(undefined)
                  setAppliedFilters({
                    search: '',
                    status: 'Default',
                    job: 'All',
                    skill: 'All',
                    experience: 'All',
                    score: [0, 10],
                    from: null,
                    to: null,
                    date: undefined
                  })
                }}
                className="h-6 text-[10px] uppercase text-muted-foreground hover:text-destructive font-bold"
              >
                Clear All
              </Button>
            </div>
          )}

          {/* Status Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 animate-in fade-in slide-in-from-top-8 duration-700 ease-out fill-mode-both delay-200">
            <div className="bg-card p-4 rounded-lg border border-l-4 border-l-emerald-500 shadow-sm">
              <p className="text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold mb-1">Selected</p>
              <div className="text-emerald-500 font-bold text-2xl">{metrics.selected}</div>
            </div>
            <div className="bg-card p-4 rounded-lg border border-l-4 border-l-amber-500 shadow-sm">
              <p className="text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold mb-1">On Hold</p>
              <div className="text-amber-500 font-bold text-2xl">{metrics.hold}</div>
            </div>
            <div className="bg-card p-4 rounded-lg border border-l-4 border-l-red-500 shadow-sm">
              <p className="text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold mb-1">Rejected</p>
              <div className="text-red-500 font-bold text-2xl">{metrics.rejected}</div>
            </div>
          </div>

          {/* Reports List / Results */}
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <div className="flex justify-between items-center mb-4">
              <TabsList className="h-11 rounded-full p-1 bg-slate-100/80 dark:bg-slate-800/50 border border-slate-200/60 dark:border-slate-700/50">
                <TabsTrigger value="detailed" className="rounded-full px-5 h-full">Detailed View</TabsTrigger>
                <TabsTrigger value="table" className="rounded-full px-5 h-full">Table View</TabsTrigger>
                <TabsTrigger value="analytics" className="rounded-full px-5 h-full">Summary Analytics</TabsTrigger>
              </TabsList>
              
              <div className="flex items-center gap-3">
                {activeTab === 'table' && (
                  <Button 
                    onClick={downloadCSV} 
                    variant="outline" 
                    className="gap-2 bg-background hover:bg-emerald-50 text-emerald-700 border-emerald-200 hover:border-emerald-300 shadow-sm h-11 rounded-full px-6 font-bold animate-in fade-in slide-in-from-right-4 duration-300"
                  >
                    <FileText className="h-4 w-4" /> Export to Excel
                  </Button>
                )}

                <div className="flex items-center gap-2.5 bg-slate-100/80 dark:bg-slate-800/50 px-4 h-11 rounded-full border border-slate-200/60 dark:border-slate-700/50 shadow-sm animate-in fade-in zoom-in duration-500">
                  <span className="text-[13px] font-bold text-slate-500 dark:text-slate-400 tracking-tight">Show</span>
                  <Select
                    value={String(reportsPerPage)}
                    onValueChange={(v) => {
                      setReportsPerPage(Number(v))
                      setReportsPage(1)
                    }}
                  >
                    <SelectTrigger className="h-8 w-[84px] rounded-full bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 text-[14px] font-extrabold text-slate-700 dark:text-slate-200 shadow-none focus:ring-2 focus:ring-primary/20 transition-all hover:border-primary/40 px-3">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="rounded-xl border-slate-200 dark:border-slate-700 shadow-xl">
                      <SelectItem value="10" className="rounded-lg focus:bg-primary/10">10</SelectItem>
                      <SelectItem value="25" className="rounded-lg focus:bg-primary/10">25</SelectItem>
                      <SelectItem value="50" className="rounded-lg focus:bg-primary/10">50</SelectItem>
                      <SelectItem value="100" className="rounded-lg focus:bg-primary/10">100</SelectItem>
                    </SelectContent>
                  </Select>
                  <span className="text-[13px] font-bold text-slate-500 dark:text-slate-400 tracking-tight">per page</span>
                </div>
              </div>
            </div>

            <TabsContent value="detailed" className="space-y-4 animate-in fade-in slide-in-from-bottom-8 duration-700 ease-out fill-mode-both delay-300">
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-4">
                  {filteredReports.length > 0 ? (
                    filteredReports.map((report: Report, idx: number) => (
                      <ReportCard
                        key={idx}
                        report={report}
                        onClick={() => setViewingReport(report)}
                      />
                    ))
                  ) : (
                    <div className="h-64 flex flex-col items-center justify-center border border-dashed rounded-2xl bg-muted/10 animate-in fade-in zoom-in duration-500">
                      <div className="bg-muted/20 p-4 rounded-full mb-4">
                        <AlertCircle className="h-10 w-10 text-muted-foreground/30" />
                      </div>
                      <p className="text-lg font-bold text-muted-foreground">No reports found</p>
                      <p className="text-sm text-muted-foreground/60 max-w-[280px] text-center mt-1">
                        Try adjusting your filters or search query to find what you're looking for.
                      </p>
                    </div>
                  )}
                </div>

              </div>
            </TabsContent>

            <TabsContent value="table" className="animate-in fade-in zoom-in-95 duration-300">

              <Card>
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Candidate</TableHead>
                        <TableHead>Date</TableHead>
                        <TableHead>Applied For</TableHead>
                        <TableHead className="text-right">Aptitude</TableHead>
                        <TableHead className="text-right">Behavioral</TableHead>
                        <TableHead className="text-right">Score</TableHead>
                        <TableHead className="text-center">Suggestion</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredReports.map((report: Report, idx: number) => (
                        <TableRow key={idx}>
                          <TableCell className="font-semibold text-slate-700 dark:text-slate-200">
                            {report.candidate_profile.candidate_name || report.filename.replace('.json', '')}
                          </TableCell>
                          <TableCell>{report.display_date_short}</TableCell>
                          <TableCell className="text-sm">{report.candidate_profile.applied_role || 'N/A'}</TableCell>
                          <TableCell className="text-right font-medium">
                            {report.aptitude_score !== undefined && report.aptitude_score !== null ? report.aptitude_score.toFixed(1) : '-'}
                          </TableCell>
                          <TableCell className="text-right font-medium">
                            {report.behavioral_score !== undefined && report.behavioral_score !== null ? report.behavioral_score.toFixed(1) : '-'}
                          </TableCell>
                          <TableCell className="text-right font-bold text-primary">{report.overall_score.toFixed(1)}</TableCell>
                          <TableCell className="text-center">
                            {isInterviewNotCompleted(report) ? (
                              <Badge
                                variant="outline"
                                className="bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/30"
                              >
                                Incomplete
                              </Badge>
                            ) : (
                              <Badge variant="outline" className={getRecommendationColor(report.overall_score)}>
                                {getRecommendationLabel(report.overall_score)}
                              </Badge>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                      {filteredReports.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={6} className="h-24 text-center">
                            No reports found.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Common Pagination Controls for Detailed and Table views */}
            {activeTab !== 'analytics' && totalPages > 1 && (
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mt-6 pt-6 border-t border-border">
                  <div className="text-sm text-muted-foreground font-medium">
                    Showing <span className="font-semibold text-foreground/80">{Math.min(reportsPerPage, totalCount)}</span> of <span className="font-semibold text-foreground/80">{totalCount}</span> reports
                  </div>
                  
                  <div className="flex flex-wrap items-center gap-6">
                    <div className="text-sm font-medium text-muted-foreground">
                      Page <span className="text-foreground/80 font-semibold">{reportsPage}</span> of {totalPages}
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setReportsPage(prev => prev - 1)}
                        disabled={reportsPage <= 1}
                        className="h-8 px-4 rounded-xl font-bold bg-background dark:bg-muted border-border transition-all shadow-sm active:scale-95 disabled:opacity-50"
                      >
                        Previous
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setReportsPage(prev => prev + 1)}
                        disabled={reportsPage >= totalPages}
                        className="h-8 px-4 rounded-xl font-bold bg-background dark:bg-muted border-border transition-all shadow-sm active:scale-95 disabled:opacity-50"
                      >
                        Next
                      </Button>
                    </div>

                    <div className="text-sm font-semibold text-foreground/80 uppercase tracking-widest hidden lg:block border-l pl-6 border-border">
                      Total {totalCount} Reports
                    </div>
                  </div>
                </div>
            )}

            <TabsContent value="analytics" className="animate-in fade-in zoom-in-95 duration-300">
              {metrics.total > 0 ? (
                <Card className="border-none shadow-xl bg-gradient-to-br from-white to-slate-50/50 dark:from-slate-900 dark:to-slate-900/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xl flex items-center gap-2">
                      <BarChart className="h-5 w-5 text-primary" />
                      Overview & Analysis
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-col lg:flex-row gap-8 items-start py-4">
                      <div className="flex-1 w-full h-[280px] relative">
                        <StatusChart data={[
                          { name: 'Selected', value: metrics.selected, color: '#10b981' },
                          { name: 'Hold', value: metrics.hold, color: '#f59e0b' },
                          { name: 'Rejected', value: metrics.rejected, color: '#ef4444' },
                          { name: 'Terminated', value: metrics.terminated, color: '#b91c1c' },
                          { name: 'Incomplete', value: metrics.incomplete, color: '#f97316' }
                        ].filter(d => d.value > 0)} />
                      </div>

                      <div className="w-full lg:w-1/3 grid grid-cols-2 gap-4">
                        <div className="bg-white/50 dark:bg-slate-800/50 p-6 rounded-2xl border border-slate-100 dark:border-slate-800 text-center flex flex-col justify-center shadow-sm hover:shadow-md transition-all">
                          <div className="text-3xl font-black text-slate-900 dark:text-slate-50 tracking-tight">{metrics.avgScore}</div>
                          <div className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mt-1">Avg Score</div>
                        </div>
                        <div className="bg-white/50 dark:bg-slate-800/50 p-6 rounded-2xl border border-slate-100 dark:border-slate-800 text-center flex flex-col justify-center shadow-sm hover:shadow-md transition-all">
                          <div className="text-3xl font-black text-slate-900 dark:text-slate-50 tracking-tight">{metrics.total}</div>
                          <div className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mt-1">Interviews</div>
                        </div>
                        <div className="bg-white/50 dark:bg-slate-800/50 p-6 rounded-2xl border border-slate-100 dark:border-slate-800 text-center flex flex-col justify-center shadow-sm hover:shadow-md transition-all">
                          <div className="text-3xl font-black text-slate-900 dark:text-slate-50 tracking-tight">{metrics.avgQuestions}</div>
                          <div className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mt-1">Avg Qs</div>
                        </div>
                        <div className="bg-white/50 dark:bg-slate-800/50 p-6 rounded-2xl border border-slate-100 dark:border-slate-800 text-center flex flex-col justify-center shadow-sm hover:shadow-md transition-all">
                          <div className="text-3xl font-black text-emerald-600 dark:text-emerald-400 tracking-tight">
                            {metrics.total > 0 ? Math.round((metrics.selected / metrics.total) * 100) : 0}%
                          </div>
                          <div className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mt-1">Success Rate</div>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <Card className="h-80 flex flex-col items-center justify-center border border-dashed rounded-3xl bg-muted/5 animate-in fade-in zoom-in duration-500">
                  <div className="bg-muted/10 p-5 rounded-full mb-4">
                    <Activity className="h-12 w-12 text-muted-foreground/20" />
                  </div>
                  <p className="text-xl font-black text-muted-foreground tracking-tight">No analysis data available</p>
                  <p className="text-sm text-muted-foreground/50 max-w-[320px] text-center mt-2 font-medium">
                    We couldn't find any reports matching your current filter criteria to generate analytics.
                  </p>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={clearAllFilters}
                    className="mt-6 rounded-full px-6 font-bold hover:bg-primary hover:text-white transition-all"
                  >
                    Clear Filters
                  </Button>
                </Card>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* FULL VIEW MODAL FOR REPORT */}
      <Dialog open={!!viewingReport} onOpenChange={(open) => !open && setViewingReport(null)}>
        <DialogContent className="w-[80vw] sm:max-w-[80vw] lg:w-[66vw] lg:max-w-[66vw] h-[85vh] lg:h-[80vh] flex flex-col p-6 overflow-hidden">
          {viewingReport && (
            <>
              <DialogHeader className="mb-4">
                <div className="flex justify-between items-start gap-4 pr-6">
                  <div className="flex flex-col items-start gap-1">
                    <DialogTitle className="text-2xl flex items-center gap-3 flex-wrap">
                      {viewingReport.candidate_profile.candidate_name || viewingReport.display_date_short}
                      {interviewNotCompleted ? (
                        <Badge className="capsule-badge border-none shadow-none text-sm bg-orange-500/15 text-orange-700 dark:text-orange-400 border-orange-500/30">
                          Suggestion: Incomplete
                        </Badge>
                      ) : (
                        <>
                          {viewingReport.overall_score > 6 && <Badge className="capsule-badge capsule-badge-success border-none shadow-none text-sm">Suggestion: Select</Badge>}
                          {(viewingReport.overall_score > 4 && viewingReport.overall_score <= 6) && <Badge className="capsule-badge capsule-badge-warning border-none shadow-none text-sm">Suggestion: Consider</Badge>}
                          {viewingReport.overall_score <= 4 && <Badge className="capsule-badge capsule-badge-destructive border-none shadow-none text-sm">Suggestion: Reject</Badge>}
                        </>
                      )}
                    </DialogTitle>
                    <DialogDescription className="text-base text-muted-foreground mt-1">
                      {viewingReport.candidate_profile.applied_role || viewingReport.filename} &middot; {viewingReport.display_date}
                    </DialogDescription>
                    {interviewNotCompleted && (
                      <div
                        role="status"
                        className={`mt-3 w-full rounded-lg border px-4 py-3 text-sm shadow-sm flex items-center gap-3 ${viewingReport.termination_reason
                            ? 'border-red-500/40 bg-red-500/10 text-red-950 dark:text-red-100'
                            : 'border-amber-500/40 bg-amber-500/10 text-amber-950 dark:text-amber-100'
                          }`}
                      >
                        <AlertCircle className="h-5 w-5 shrink-0" />
                        <div>
                          <p className="font-bold">
                            {viewingReport.termination_reason ? 'Interview Terminated' : 'Interview Incomplete'}
                          </p>
                          <p className="mt-0.5 opacity-90">
                            {viewingReport.termination_reason
                              ? `Reason: ${viewingReport.termination_reason}`
                              : 'The candidate exited or terminated the session before answering questions.'}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="flex gap-6 items-center mr-4">
                    <div className="text-right border-l pl-6 border-border hidden sm:block">
                      <div className="text-xs text-slate-500 uppercase tracking-wider font-semibold">Aptitude</div>
                      <div className="font-bold text-2xl text-slate-700 dark:text-slate-200">
                        {viewingReport.aptitude_score !== undefined && viewingReport.aptitude_score !== null ? (
                          <>{viewingReport.aptitude_score.toFixed(1)}<span className="text-sm text-slate-400 font-normal">/10</span></>
                        ) : (
                          <span className="text-2xl font-semibold text-muted-foreground">—</span>
                        )}
                      </div>
                    </div>
                    <div className="text-right border-l pl-6 border-border hidden sm:block">
                      <div className="text-xs text-slate-500 uppercase tracking-wider font-semibold">Behavioral</div>
                      <div className="font-bold text-2xl text-slate-700 dark:text-slate-200">
                        {viewingReport.behavioral_score !== undefined && viewingReport.behavioral_score !== null ? (
                          <>{viewingReport.behavioral_score.toFixed(1)}<span className="text-sm text-slate-400 font-normal">/10</span></>
                        ) : (
                          <span className="text-2xl font-semibold text-muted-foreground">—</span>
                        )}
                      </div>
                    </div>
                    <div className="text-right border-l pl-6 border-border">
                      <div className="text-xs text-primary/80 uppercase tracking-wider font-semibold">Technical Score</div>
                      <div className="font-bold text-3xl text-primary">{viewingReport.overall_score.toFixed(1)}<span className="text-base text-primary/60 font-normal">/10</span></div>
                    </div>
                  </div>
                </div>
              </DialogHeader>

              <Separator className="mb-2 shrink-0" />

              <div className="flex-1 overflow-y-auto pr-2 space-y-6 pb-6 mt-4">
                
                {/* Skill Match Section */}
                <div className="bg-primary/5 border border-primary/10 rounded-2xl p-4 animate-in fade-in slide-in-from-top-2 duration-500">
                  <div className="flex flex-col sm:flex-row gap-4 items-start">
                    <div className="flex items-center gap-2 shrink-0 pt-1">
                      <div className="w-1.5 h-6 bg-primary rounded-full" />
                      <span className="text-xs font-black uppercase tracking-widest text-primary/80">Skill Match:</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {(() => {
                        try {
                          const rawSkills = viewingReport.candidate_profile.primary_skill || viewingReport.candidate_profile.skills;
                          const skillsArray = typeof rawSkills === 'string' ? JSON.parse(rawSkills) : rawSkills;
                          
                          if (Array.isArray(skillsArray) && skillsArray.length > 0) {
                            return skillsArray.map((skill, i) => (
                              <Badge 
                                key={i} 
                                variant="secondary" 
                                className={`text-[11px] font-bold px-3 py-1 rounded-lg border-none shadow-sm
                                  ${skillFilter !== 'All' && (skill || '').toLowerCase().includes(skillFilter.replace('_', ' ').toLowerCase())
                                    ? 'bg-primary text-primary-foreground' 
                                    : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                                  }`}
                              >
                                {skill}
                              </Badge>
                            ));
                          }
                        } catch (e) {
                          // Fallback if not a JSON array
                          if (viewingReport.candidate_profile.primary_skill) {
                            return <Badge variant="secondary" className="bg-primary text-primary-foreground font-bold">{viewingReport.candidate_profile.primary_skill}</Badge>
                          }
                        }
                        return <span className="text-sm text-muted-foreground italic font-medium">No detected skills for this profile.</span>;
                      })()}
                    </div>
                  </div>
                </div>

                {/* Video Interview Recording */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold flex items-center gap-2 text-blue-600">
                      <Video className="h-5 w-5" />
                      Interview Video Recording
                    </h3>
                    {viewingReport.video_url && (
                      <a
                        href={viewingReport.video_url?.startsWith('http') ? viewingReport.video_url : `${API_BASE_URL}${viewingReport.video_url}`}
                        download={`interview_${viewingReport.id}_recording.webm`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-blue-600 transition-colors bg-slate-50 hover:bg-blue-50 border border-slate-200 hover:border-blue-200 px-3 py-1.5 rounded-lg"
                      >
                        <Download className="h-3.5 w-3.5" />
                        Download
                      </a>
                    )}
                  </div>
                  {viewingReport.video_url ? (
                    <div className="bg-slate-900 rounded-2xl overflow-hidden shadow-xl aspect-video relative group">
                      <video
                        key={viewingReport.id}
                        src={viewingReport.video_url?.startsWith('http') ? viewingReport.video_url : `${API_BASE_URL}${viewingReport.video_url}`}
                        controls
                        preload="metadata"
                        className="w-full h-full"
                        crossOrigin="use-credentials"
                        onError={(e) => {
                          // Hide broken player and show fallback
                          const target = e.currentTarget
                          const parent = target.closest('.video-wrapper') as HTMLElement
                          if (parent) {
                            parent.innerHTML = `<div class="flex flex-col items-center justify-center h-full text-center p-8"><svg class="h-10 w-10 text-slate-500 mb-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3l18 18M17 5H7a2 2 0 00-2 2v10a2 2 0 002 2h10M23 7l-6 4 6 4V7z"/></svg><p class="text-sm font-semibold text-slate-300">Video could not be loaded.</p><p class="text-xs text-slate-500 mt-1">The recording may still be processing or unavailable.</p></div>`
                          }
                        }}
                      />
                      <div className="absolute top-4 left-4 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity">
                        <span className="inline-flex items-center gap-2 bg-black/50 backdrop-blur-md text-white text-xs font-bold px-3 py-1.5 rounded-full border border-white/20">
                          <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
                          Session Recorded
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-muted/30 border-2 border-dashed rounded-2xl p-8 flex flex-col items-center justify-center text-center">
                      <CameraOff className="h-10 w-10 text-muted-foreground/40 mb-3" />
                      <p className="text-sm font-medium text-muted-foreground">No video recording available for this session.</p>
                      <p className="text-xs text-muted-foreground/60 mt-1">The candidate may have blocked camera access, or recording failed during the interview.</p>
                    </div>
                  )}
                </div>

                {/* Section Score Breakdown */}
                <div className="space-y-3">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Activity className="h-5 w-5 text-primary" />
                    Section Score Breakdown
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <CategoryScoreCard title="📊 Aptitude Score" score={viewingReport.aptitude_score ?? undefined} />
                    <CategoryScoreCard
                      title="💻 Technical Score"
                      score={(viewingReport.technical_score ?? viewingReport.tech_score) ?? undefined}
                      showNotAvailable={interviewNotCompleted}
                    />
                    <CategoryScoreCard
                      title="🧠 Behavioral Score"
                      score={viewingReport.behavioral_score ?? undefined}
                      showNotAvailable={interviewNotCompleted}
                    />
                  </div>


                </div>

                <div className="space-y-4 mb-8">
                  <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Activity className="h-5 w-5 text-primary" />
                    Performance Analytics
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                    {/* Chart 1: Evaluation Radar */}
                    <div className="bg-card border rounded-xl p-4 h-[250px] shadow-sm flex flex-col items-center">
                      <span className="text-sm font-semibold text-muted-foreground w-full text-left mb-2">Competency Radar</span>
                      {radarShowsPlaceholder ? (
                        <div className="flex flex-1 w-full items-center justify-center text-center text-sm text-muted-foreground px-4">
                          No data available.
                        </div>
                      ) : (
                        <ResponsiveContainer width="100%" height="100%">
                          <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                            <PolarGrid stroke="var(--border)" />
                            <PolarAngleAxis dataKey="subject" tick={{ fill: 'currentColor', fontSize: 11 }} />
                            <PolarRadiusAxis angle={30} domain={[0, 10]} tick={{ fontSize: 10 }} />
                            <Radar name="Score" dataKey="A" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.6} />
                            <RechartsTooltip contentStyle={{ borderRadius: '8px', border: '1px solid var(--border)' }} />
                          </RadarChart>
                        </ResponsiveContainer>
                      )}
                    </div>

                    {/* Chart 2: Tech vs Comm Line */}
                    <div className="bg-card border rounded-xl p-4 h-[250px] shadow-sm flex flex-col items-center">
                      <span className="text-sm font-semibold text-muted-foreground w-full text-left mb-2">Progression</span>
                      {progressionShowsPlaceholder ? (
                        <div className="flex flex-1 w-full items-center justify-center text-center text-sm text-muted-foreground px-4">
                          No progression data — interview was not completed.
                        </div>
                      ) : (
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={lineData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                            <XAxis dataKey="name" tick={{ fill: 'currentColor', fontSize: 11 }} axisLine={false} tickLine={false} />
                            <YAxis domain={[0, 10]} tick={{ fill: 'currentColor', fontSize: 11 }} axisLine={false} tickLine={false} />
                            <RechartsTooltip contentStyle={{ borderRadius: '8px', border: '1px solid var(--border)' }} />
                            <Line type="monotone" dataKey="Tech" stroke="hsl(var(--primary))" strokeWidth={3} dot={{ r: 4 }} />
                            <Line type="monotone" dataKey="Comm" stroke="#10b981" strokeWidth={3} dot={{ r: 4 }} />
                          </LineChart>
                        </ResponsiveContainer>
                      )}
                    </div>

                    {/* Chart 3: Detailed Metrics */}
                    <div className="bg-card border rounded-xl p-4 h-[250px] shadow-sm flex flex-col">
                      <span className="text-sm font-semibold text-muted-foreground w-full text-left mb-2">Detailed Metrics (Avg)</span>
                      <div className="flex-1 min-h-0">
                        <DetailedMetricsChart report={viewingReport} showNoData={interviewNotCompleted} />
                      </div>
                    </div>

                    {/* Chart 4: Skill Proficiency Distribution */}
                    <div className="bg-card border rounded-xl p-4 h-[250px] shadow-sm flex flex-col">
                      <span className="text-sm font-semibold text-muted-foreground w-full text-left mb-2">Skill Proficiency</span>
                      <div className="flex-1 min-h-0">
                        <SkillProficiencyChart report={viewingReport} />
                      </div>
                    </div>
                  </div>

                  {/* Skill Proficiency Evaluation Justifications */}
                  <div className="flex flex-col gap-4 mb-8">
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                      <Activity className="h-5 w-5 text-primary" />
                      Skill Proficiency Evaluation
                    </h3>
                    <div className="grid grid-cols-1 gap-4">
                      {(() => {
                        try {
                          if (viewingReport.evaluated_skills) {
                            const parsedSkills = JSON.parse(viewingReport.evaluated_skills);
                            if (Array.isArray(parsedSkills) && parsedSkills.length > 0) {
                              return parsedSkills.map((skill, index) => (
                                <div key={index} className="bg-card border rounded-xl p-5 shadow-sm">
                                  <div className="flex justify-between items-center mb-2">
                                    <h4 className="font-semibold text-md text-foreground">{skill.skillName || 'Unknown Skill'}</h4>
                                    <Badge variant="secondary" className="font-bold tabular-nums">
                                      {skill.score || 0}/10
                                    </Badge>
                                  </div>
                                  <p className="text-sm text-muted-foreground leading-relaxed">
                                    {skill.justification || 'No justification provided.'}
                                  </p>
                                </div>
                              ));
                            }
                          }
                        } catch (e) {
                          return <p className="text-sm text-muted-foreground">Unable to load skill proficiency details.</p>;
                        }
                        return <p className="text-sm text-muted-foreground">No specific skill evaluations recorded for this interview.</p>;
                      })()}
                    </div>
                  </div>
                </div>

                <div className="flex flex-col gap-4">
                  <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                      <FileText className="h-5 w-5 text-primary" />
                      Question Analysis
                    </h3>
                    <div className="flex gap-3 shrink-0">
                      <Button onClick={() => downloadFile(JSON.stringify(viewingReport, null, 2), viewingReport.filename, 'json')} variant="outline" className="bg-card hover:bg-muted shadow-sm">
                        <Download className="h-4 w-4 mr-2" /> Export JSON
                      </Button>
                      <Button onClick={() => downloadFile(generateTextReport(viewingReport), viewingReport.filename.replace('.json', '.txt'), 'txt')} className="shadow-sm">
                        <FileText className="h-4 w-4 mr-2" /> Download Report
                      </Button>
                    </div>
                  </div>
                  {interviewNotCompleted && (
                    <p className="mt-2 text-xs text-amber-700 dark:text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-md px-3 py-2 inline-block">
                      Note: This report has incomplete data as the candidate did not finish the interview.
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant={reportView === 'technical' ? 'default' : 'outline'}
                      onClick={() => setReportView('technical')}
                      size="sm"
                      className="rounded-full"
                    >
                      Technical Questions
                    </Button>
                    <Button
                      variant={reportView === 'behavioral' ? 'default' : 'outline'}
                      onClick={() => setReportView('behavioral')}
                      size="sm"
                      className="rounded-full"
                    >
                      Behavioral Questions
                    </Button>
                    <Button
                      variant={reportView === 'aptitude' ? 'default' : 'outline'}
                      onClick={() => setReportView('aptitude')}
                      size="sm"
                      className="rounded-full"
                    >
                      Aptitude Questions
                    </Button>
                  </div>
                  <ScrollArea className="h-[400px] w-full pr-4 border rounded-xl bg-card">
                    {reportView === 'aptitude' ? (
                      <div className="p-0">
                        <table className="w-full text-sm text-left">
                          <thead className="bg-muted/50 sticky top-0 z-10 border-b">
                            <tr>
                              <th className="px-4 py-3 font-semibold w-12 text-center">#</th>
                              <th className="px-4 py-3 font-semibold">Question</th>
                              <th className="px-4 py-3 font-semibold">Candidate's Answer</th>
                              <th className="px-4 py-3 font-semibold w-32 text-center">Result</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y">
                            {(viewingReport.aptitude_question_evaluations ?? []).map((q, i) => (
                              <tr key={i} className="hover:bg-muted/30 transition-colors">
                                <td className="px-4 py-4 text-center font-medium text-muted-foreground">{i + 1}</td>
                                <td className="px-4 py-4">{cleanQuestionText(q.question)}</td>
                                <td className="px-4 py-4 text-muted-foreground">{q.answer || <span className="italic text-muted-foreground/50">No answer provided</span>}</td>
                                <td className="px-4 py-4 text-center">
                                  {q.correct ? (
                                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400 font-medium">
                                      <CheckCircle2 className="w-4 h-4" /> Correct
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400 font-medium">
                                      <XCircle className="w-4 h-4" /> Incorrect
                                    </span>
                                  )}
                                </td>
                              </tr>
                            ))}
                            {(viewingReport.aptitude_question_evaluations?.length === 0) && (
                              <tr>
                                <td colSpan={4} className="px-4 py-12 text-center text-muted-foreground italic">
                                  No aptitude questions found for this interview.
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                        {viewingReport.question_evaluations
                          .filter(q => (q.question_type || 'technical') === reportView)
                          .map((q, i) => {
                            const qType = q.question_type || 'technical';
                            const unanswered = isAnswerEmpty(q.answer) && getDisplayedQuestionScore(q) === 0;
                            return (
                              <div
                                key={i}
                                className="bg-muted/30 p-4 rounded-xl border cursor-pointer hover:bg-muted/70 hover:border-primary/40 transition-colors group"
                                onClick={() => setSelectedQuestion(q)}
                              >
                                <div className="flex justify-between items-start mb-3 gap-2">
                                  <div className="flex items-center gap-2">
                                    <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold">
                                      {i + 1}
                                    </span>
                                    <span className={`text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${qType === 'behavioral'
                                      ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
                                      : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                                      }`}>
                                      {qType === 'behavioral' ? 'Behavioral' : 'Technical'}
                                    </span>
                                  </div>
                                  <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0">
                                    <Badge variant="secondary" className="font-bold tabular-nums">
                                      {q.evaluation?.technical_accuracy ?? q.evaluation?.overall ?? 0}/10
                                    </Badge>
                                    {unanswered && (
                                      <Badge variant="outline" className="text-xs font-medium text-muted-foreground border-muted-foreground/25 bg-muted/60">
                                        Not Answered
                                      </Badge>
                                    )}
                                  </div>
                                </div>
                                <p className="text-sm font-medium mb-3 line-clamp-2 leading-relaxed">{cleanQuestionText(q.question)}</p>
                                <div className="flex gap-4">
                                  <div className="flex flex-col gap-1 w-1/2">
                                    <span className="text-xs font-semibold text-green-600 dark:text-green-400">Top Strength</span>
                                    <p className="text-xs text-muted-foreground line-clamp-1">{q.evaluation.strengths?.[0] || 'N/A'}</p>
                                  </div>
                                  <div className="flex flex-col gap-1 w-1/2">
                                    <span className="text-xs font-semibold text-red-600 dark:text-red-400">Area to Improve</span>
                                    <p className="text-xs text-muted-foreground line-clamp-1">{q.evaluation.weaknesses?.[0] || 'N/A'}</p>
                                  </div>
                                </div>
                              </div>
                            )
                          }
                          )}
                        {viewingReport.question_evaluations.filter(q => (q.question_type || 'technical') === reportView).length === 0 && (
                          <div className="col-span-full py-20 text-center text-muted-foreground italic">
                            No {reportView} questions found for this interview.
                          </div>
                        )}
                      </div>
                    )}
                  </ScrollArea>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div >
  )
}
