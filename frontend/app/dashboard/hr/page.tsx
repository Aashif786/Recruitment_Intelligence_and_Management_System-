'use client'

/**
 * RIMS HR Dashboard
 * Forced refresh: 2026-04-15
 */

import React, { useEffect, useState, useMemo } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import Link from 'next/link'
import { APIClient } from '@/app/dashboard/lib/api-client'
import useSWR from 'swr'
import { fetcher } from '@/app/dashboard/lib/swr-fetcher'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/app/dashboard/lib/auth-context'
import {
  Briefcase,
  Users,
  Calendar,
  CheckCircle,
  TrendingUp,
  Clock,
  ArrowRight,
  Search,
  Filter,
  X,
  Award,
  RotateCw,
  RotateCcw,
  LayoutDashboard,
  FileText,
  AlertCircle
} from 'lucide-react'
import { PageHeader } from '@/components/page-header'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// Lazy-load the entire chart component — defers Recharts bundle (~200KB)
const DashboardChart = dynamic(
  () => import('@/components/dashboard-chart').then(mod => ({ default: mod.DashboardChart })),
  {
    ssr: false,
    loading: () => (
      <div className="h-[300px] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }
)
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'

interface DashboardData {
  recruitment_metrics: {
    total_candidates: number
    shortlisted_candidates: number
    interviewed_candidates: number
    offers_released: number
    hiring_success_rate: number
  }
  candidate_metrics: {
    avg_job_compatibility: number
    avg_aptitude_score: number
    avg_interview_score: number
    avg_composite_score: number
  }
  chart_data: { name: string; value: number }[]
  recent_interviews: any[]
}

export default function HRDashboard() {
  const router = useRouter()
  const { user, isLoading: authLoading } = useAuth()
  
  const [filters, setFilters] = useState<any>({
    search: '',
    date: '',
    status: 'all'
  })
  
  const [jobFilter, setJobFilter] = useState('all')
  const [debouncedSearch, setDebouncedSearch] = useState(filters.search)

  const { data: dashboardData, error: dashboardError, isLoading: dashboardLoading } = useSWR<DashboardData>(
    `/api/analytics/dashboard?${new URLSearchParams({
      ...(jobFilter !== 'all' ? { job_id: jobFilter } : {}),
      ...(filters.status !== 'all' ? { status: filters.status } : {}),
      ...(debouncedSearch ? { search: debouncedSearch } : {})
    }).toString()}`, 
    (url: string) => fetcher<DashboardData>(url),
    { keepPreviousData: true }
  )
  const { data: jobs = [] } = useSWR<any[]>(
    '/api/jobs',
    (url: string) => fetcher<any[]>(url),
    { keepPreviousData: true }
  )

  const isSuperAdmin = user?.role === 'super_admin'
  const { data: pendingApprovals = [] } = useSWR<any[]>(
    isSuperAdmin ? '/api/auth/pending-approvals' : null,
    (url: string) => fetcher<any[]>(url),
    {} // no polling — mutations call mutate() explicitly
  )

  useEffect(() => {
    if (!authLoading && user && user.role === 'candidate') {
      router.push('/jobs')
    }
  }, [user, authLoading, router])

  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(filters.search)
    }, 500)
    return () => clearTimeout(timer)
  }, [filters.search])

  useEffect(() => {
    setCurrentPage(1)
  }, [debouncedSearch, filters.date, filters.status])

  // We use SWR for the initial filtered interviews as well
  const filterQuery = useMemo(() => {
    const params = new URLSearchParams()
    if (debouncedSearch) params.append('search', debouncedSearch)
    if (filters.date) params.append('date', filters.date)
    if (filters.status && filters.status !== 'all') params.append('status', filters.status)
    if (jobFilter && jobFilter !== 'all') params.append('job_id', jobFilter)
    
    // Pagination params
    params.append('skip', String((currentPage - 1) * pageSize))
    params.append('limit', String(pageSize))
    
    return params.toString()
  }, [debouncedSearch, filters.date, filters.status, jobFilter, currentPage, pageSize])

  const { data: paginatedInterviews, isValidating: isFiltering, mutate: mutateInterviews } = useSWR<{ items: any[], total: number }>(
    `/api/analytics/interviews${filterQuery ? `?${filterQuery}` : ''}`,
    (url: string) => fetcher<{ items: any[], total: number }>(url),
    { keepPreviousData: true }
  )

  // ... helper calculations ...
  const r_metrics = useMemo(() => {
    const d = dashboardData || {}
    // Check for new flat structure first
    if ('total_applications' in d) {
      return {
        total_candidates: (d as any).total_applications || 0,
        shortlisted_candidates: (d as any).total_interviews || 0,
        interviewed_candidates: (d as any).completed_interviews || 0,
        offers_released: (d as any).offers_released || 0,
        hiring_success_rate: (d as any).success_rate || 0
      }
    }
    // Fallback to legacy nested structure or zero defaults
    const nested = (d as any).recruitment_metrics || {}
    return {
      total_candidates: nested.total_candidates || 0,
      shortlisted_candidates: nested.shortlisted_candidates || 0,
      interviewed_candidates: nested.interviewed_candidates || 0,
      offers_released: nested.offers_released || 0,
      hiring_success_rate: nested.hiring_success_rate || 0
    }
  }, [dashboardData])
  
  const c_metrics = useMemo(() => {
    const d = dashboardData || {}
    // Check for new flat structure first
    if ('average_score' in d) {
      return {
        avg_job_compatibility: 0,
        avg_aptitude_score: 0,
        avg_interview_score: 0,
        avg_composite_score: (d as any).average_score || 0
      }
    }
    // Fallback to legacy nested structure or zero defaults
    const nested = (d as any).candidate_metrics || {}
    return {
      avg_job_compatibility: nested.avg_job_compatibility || 0,
      avg_aptitude_score: nested.avg_aptitude_score || 0,
      avg_interview_score: nested.avg_interview_score || 0,
      avg_composite_score: nested.avg_composite_score || 0
    }
  }, [dashboardData])

  const chartData = (dashboardData as any)?.chart_data || []
  const recentInterviews = useMemo(() => {
    if (paginatedInterviews?.items && Array.isArray(paginatedInterviews.items)) {
      return paginatedInterviews.items
    }
    const legacy = (dashboardData as any)?.recent_interviews
    return Array.isArray(legacy) ? legacy : []
  }, [paginatedInterviews, dashboardData])

  const handleReset = () => {
    setFilters({
      search: '',
      date: '',
      status: 'all'
    })
    setJobFilter('all')
    setCurrentPage(1)
    setPageSize(10)
  }


  const COLORS = ['#3b82f6', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444'];

  // We've removed the blocking error/loading UI to ensure the dashboard shell always loads.
  // Metrics will fallback to zero defaults handled in useMemos.

  return (
    <div className="p-4 md:p-0 space-y-8">
      {/* Header */}
      <PageHeader 
        title="Recruitment Dashboard"
        description="AI-Powered Hiring Intelligence"
        icon={LayoutDashboard}
      />



      {isSuperAdmin && pendingApprovals.length > 0 && (
        <Card className="shadow-none border border-border dark:border-slate-800 bg-card dark:bg-slate-900 rounded-xl p-6 animate-in fade-in duration-300">
          <CardHeader>
            <div className="flex items-center justify-between gap-4">
              <div>
                <CardTitle className="text-foreground/80 dark:text-slate-200">Pending HR Approvals</CardTitle>
                <CardDescription className="text-muted-foreground">Review newly registered HR users before they can login.</CardDescription>
              </div>
              <Badge variant="secondary" className="bg-primary text-primary-foreground">
                {pendingApprovals.length}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-sm text-muted-foreground mb-4">
              {pendingApprovals.length > 0
                ? `There ${pendingApprovals.length === 1 ? 'is' : 'are'} ${pendingApprovals.length} account${pendingApprovals.length === 1 ? '' : 's'} waiting for approval.`
                : 'No pending HR approvals at the moment.'}
            </p>
            <Link href="/dashboard/hr/approvals">
              <Button className="bg-primary hover:bg-primary/90 text-primary-foreground shadow-md hover:shadow-lg transition-all">
                Review Pending HR Approvals
              </Button>
            </Link>
          </CardContent>
        </Card>
      )}

      {/* Stats Cards AI Enhanced */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <Link href="/dashboard/hr/applications" className="block cursor-pointer">
          <StatsCard
            title="Total Candidates"
            value={r_metrics.total_candidates}
            icon={Users}
            color="text-primary"
            bg="bg-primary/10"
          />
        </Link>
        <StatsCard
          title="Hiring Success"
          value={`${r_metrics.hiring_success_rate}%`}
          icon={TrendingUp}
          color="text-emerald-600"
          bg="bg-emerald-500/10"
        />
        <StatsCard
          title="Avg Candidate Score"
          value={c_metrics.avg_composite_score}
          icon={Award}
          color="text-amber-600"
          bg="bg-amber-500/10"
        />
        <StatsCard
          title="Offer Letters Sent"
          subtitle="Candidates who received an offer"
          value={r_metrics.offers_released}
          icon={CheckCircle}
          color="text-blue-600"
          bg="bg-blue-500/10"
        />
      </div>

      {/* Charts & Tables Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

        {/* Chart Section */}
        <div className="lg:col-span-2 animate-in fade-in duration-500 delay-300">
          <Card className="h-full shadow-none border border-border dark:border-slate-800 bg-card dark:bg-slate-900 rounded-xl">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-foreground/80 dark:text-slate-200">Application Pipeline</CardTitle>
                  <CardDescription className="text-muted-foreground">Distribution of candidates by status</CardDescription>
                </div>
                <div className="p-2 bg-muted/20 text-blue-600 rounded-lg">
                  <TrendingUp className="h-5 w-5" />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="h-[300px] w-full">
                <DashboardChart data={chartData} />
              </div>
            </CardContent>
          </Card>
          
        </div>

        {/* Recent Activity / Quick Actions */}
        <div className="space-y-6 animate-in fade-in duration-500 delay-500">
          <Card className="shadow-none border border-border dark:border-slate-800 bg-card dark:bg-slate-900 rounded-xl">
            <CardHeader>
              <CardTitle className="text-foreground/80 dark:text-slate-200">Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <ActionButton href="/dashboard/hr/applications" label="Review Applications" />
              <ActionButton href="/dashboard/hr/pipeline" label="Hiring Pipeline" />
              <ActionButton href="/dashboard/hr/reports" label="View Reports" />
              <ActionButton href="/dashboard/onboarding" label="Onboarding" />
              <ActionButton href="/dashboard/hr/tickets" label="Resolve Tickets" />
              <ActionButton href="/dashboard/settings" label="Settings" />
            </CardContent>
          </Card>
        </div>
      </div>
onb
      {/* Recent Interviews Table */}
      <Card className="shadow-none border border-border dark:border-slate-800 bg-card dark:bg-slate-900 rounded-xl animate-in fade-in duration-500 delay-700">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-foreground/80 dark:text-slate-200">Recent Interviews</CardTitle>
              <CardDescription>Upcoming and recently completed sessions</CardDescription>
            </div>
            <Clock className="h-5 w-5 text-muted-foreground" />
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Filter Bar */}
          <div className="flex flex-col md:flex-row gap-4 p-4 bg-muted/50 dark:bg-slate-900/50 rounded-xl border border-border dark:border-slate-800 items-center">
            <div className="flex-1 w-full relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search candidates, roles, or IDs..."
                value={filters.search}
                onChange={(e) => setFilters({ ...filters, search: e.target.value })}
                className="bg-card dark:bg-slate-950 h-10 pl-10 pr-10 border-border focus:ring-primary shadow-sm"
              />
              {isFiltering && (
                <RotateCw className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-primary animate-spin" />
              )}
            </div>

            {/* Job Filter Addition */}
            <div className="w-full md:w-48">
              <Select
                value={jobFilter}
                onValueChange={setJobFilter}
              >
                <SelectTrigger className="bg-card dark:bg-slate-950 h-10 border-border shadow-sm">
                   <Briefcase className="h-4 w-4 mr-2 text-muted-foreground" />
                   <SelectValue placeholder="All Jobs" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Jobs</SelectItem>
                  {(jobs || []).map((job) => (
                    <SelectItem key={job.id} value={job.id.toString()}>
                      {job.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="w-full md:w-48">
              <Select
                value={filters.status}
                onValueChange={(value) => setFilters({ ...filters, status: value })}
              >
                <SelectTrigger className="bg-card dark:bg-slate-950 h-10 border-border shadow-sm">
                  <SelectValue placeholder="All Statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  <SelectItem value="not_started">Pending</SelectItem>
                  <SelectItem value="in_progress">In Progress</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="terminated">Terminated</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="w-full md:w-32">
              <Select
                value={String(pageSize)}
                onValueChange={(value) => setPageSize(Number(value))}
              >
                <SelectTrigger className="bg-card dark:bg-slate-950 h-10 border-border shadow-sm">
                  <span className="text-xs text-muted-foreground mr-2">Show:</span>
                  <SelectValue placeholder="10" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="10">10</SelectItem>
                  <SelectItem value="20">20</SelectItem>
                  <SelectItem value="50">50</SelectItem>
                  <SelectItem value="100">100</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button
              variant="outline"
              size="icon"
              onClick={handleReset}
              className="h-10 w-10 shrink-0 border-border hover:bg-slate-100 dark:hover:bg-slate-800 transition-all shadow-sm"
              title="Reset all filters"
            >
              <RotateCcw className="h-4 w-4 text-muted-foreground" />
            </Button>
          </div>

          {recentInterviews.length > 0 ? (
            <div className="relative">
              {isFiltering && (
                <div className="absolute inset-0 bg-background/20 backdrop-blur-[1px] z-10 flex items-center justify-center rounded-md">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                </div>
              )}
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Candidate ID</TableHead>
                    <TableHead>Candidate</TableHead>
                    <TableHead>Job Role</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentInterviews.map((interview: any) => (
                    <TableRow key={interview.id} className="group hover:bg-muted/50 transition-colors">
                      <TableCell className="font-mono text-sm text-muted-foreground">
                        {interview.test_id || 'N/A'}
                      </TableCell>
                      <TableCell className="font-medium">{interview.candidate_name}</TableCell>
                      <TableCell>{interview.job_title}</TableCell>
                      <TableCell>{new Date(interview.date).toLocaleDateString()}</TableCell>
                      <TableCell>
                        <Badge variant={
                          interview.status === 'completed' ? 'default' :
                            interview.status === 'scheduled' ? 'secondary' : 'outline'
                        } className={
                          interview.status === 'completed' ? 'bg-primary/10 text-primary hover:bg-primary/20 ' :
                            interview.status === 'scheduled' ? 'bg-secondary/10 text-secondary hover:bg-secondary/20 ' : ''
                        }>
                          {interview.status.replace('_', ' ')}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Link 
                          href={interview.report_id ? `/dashboard/hr/reports?search=${encodeURIComponent(interview.candidate_name)}&reportId=${interview.report_id}` : `/dashboard/hr/reports`} 
                          className="text-primary hover:underline text-sm font-medium"
                        >
                          View Details
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              
              {/* Pagination Controls */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mt-6 pt-6 border-t border-slate-100 dark:border-slate-800">
                <div className="text-sm text-muted-foreground">
                  Showing <span className="font-semibold text-foreground/80 dark:text-slate-200">{Math.min(pageSize, paginatedInterviews?.total || recentInterviews.length)}</span> of <span className="font-semibold text-foreground/80 dark:text-slate-200">{paginatedInterviews?.total || recentInterviews.length}</span> candidates
                </div>
                <div className="flex items-center gap-4">
                   <div className="text-sm font-medium text-muted-foreground mr-2">
                     Page <span className="text-foreground">{currentPage}</span> of {Math.ceil((paginatedInterviews?.total || 1) / pageSize)}
                   </div>
                   <div className="flex items-center gap-2">
                     <Button
                       variant="outline"
                       size="sm"
                       disabled={currentPage === 1 || isFiltering}
                       onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                       className="h-8 shadow-sm"
                     >
                       Previous
                     </Button>
                     <Button
                       variant="outline"
                       size="sm"
                       disabled={currentPage >= Math.ceil((paginatedInterviews?.total || 0) / pageSize) || isFiltering}
                       onClick={() => setCurrentPage(prev => prev + 1)}
                       className="h-8 shadow-sm"
                     >
                       Next
                     </Button>
                   </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground border-2 border-dashed border-muted rounded-lg">
              <div className="p-3 bg-muted w-fit rounded-full mx-auto mb-3">
                <Search className="h-6 w-6" />
              </div>
              <p className="font-medium">No interviews match your filters.</p>
              <Button variant="link" onClick={handleReset} className="text-primary">Clear all filters</Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

const StatsCard = React.memo(({ title, subtitle, value, icon: Icon, color, bg }: any) => {
  return (
    <Card className="shadow-sm hover:shadow-lg transition-all duration-300 border-border bg-card group hover:-translate-y-1">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <CardTitle className="text-base font-bold text-muted-foreground group-hover:text-foreground transition-colors">
            {title}
          </CardTitle>
          {subtitle && (
            <p className="text-xs text-muted-foreground/70 mt-0.5">{subtitle}</p>
          )}
        </div>
        <div className={`p-2 rounded-full ${bg}`}>
          <Icon className={`h-4 w-4 ${color}`} />
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold text-foreground dark:text-white mt-1">{value}</div>
      </CardContent>
    </Card>
  )
})
StatsCard.displayName = 'StatsCard'

const ActionButton = React.memo(({ href, label }: { href: string, label: string }) => {
  return (
    <Link href={href} className="block group">
      <Button 
        variant="outline" 
        className="w-full justify-between text-foreground hover:bg-primary/5 hover:text-primary focus:bg-primary/5 focus:text-primary active:bg-primary/10 active:text-primary border-border hover:border-primary/40 transition-all"
      >
        {label}
        <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
      </Button>
    </Link>
  )
})
ActionButton.displayName = 'ActionButton'
