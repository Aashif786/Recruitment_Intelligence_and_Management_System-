// API Client - Last Updated: 2026-04-10
import { API_BASE_URL } from '@/lib/config'
import { toast } from 'sonner'

const MUTATION_REVALIDATION_PREFIXES = [
  '/api/auth/pending-approvals',
  '/api/analytics/dashboard',
  '/api/applications',
  '/api/applications/pending-count',
  '/api/decisions',
  '/api/jobs',
  '/api/notifications',
  '/api/tickets',
] as const

export function revalidateDashboardData() {
  if (typeof window === 'undefined') {
    return
  }

  window.dispatchEvent(
    new CustomEvent('rims:data-mutated', {
      detail: { keys: [...MUTATION_REVALIDATION_PREFIXES] },
    }),
  )
}

export class APIClient {
  private static MAX_RETRIES = 3
  private static TIMEOUT_MS = 120000 // Increased to 120s globally for heavy tasks

  private static createRequestId(): string {
    if (typeof window !== 'undefined' && typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
      return crypto.randomUUID()
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`
  }

  private static isPublicEndpoint(endpoint: string): boolean {
    const normalized = endpoint.startsWith('/') ? endpoint : `/${endpoint}`
    return (
      normalized.startsWith('/api/jobs/public') ||
      normalized.startsWith('/api/onboarding/') ||
      normalized === '/api/applications/apply' ||
      normalized === '/api/applications/extract-basic-info' ||
      normalized === '/api/support/ticket'
    )
  }

  private static getHeaders(isMultipart = false, endpoint?: string): Record<string, string> {
    const headers: Record<string, string> = {}
    if (!isMultipart) {
      headers['Content-Type'] = 'application/json'
    }
    if (typeof window !== 'undefined' && !(endpoint && this.isPublicEndpoint(endpoint))) {
      const isInterviewRoute = window.location.pathname.includes('/interview')
      if (isInterviewRoute) {
        const interviewToken = localStorage.getItem('interview_token')
        if (interviewToken) {
          headers['Authorization'] = `Bearer ${interviewToken}`
        }
      }
    }
    headers['X-Request-Source'] = 'rims-frontend'
    return headers
  }

  private static async fetchWithRetry(url: string, options: RequestInit, retries = 0, customTimeoutMs?: number): Promise<Response> {
    const controller = new AbortController()
    const timeout = customTimeoutMs ?? this.TIMEOUT_MS
    const id = setTimeout(() => controller.abort(), timeout)
    
    try {
      const response = await fetch(url, { ...options, signal: controller.signal })
      clearTimeout(id)
      return response
    } catch (err: any) {
      clearTimeout(id)
      const isTimeout = err.name === 'AbortError'
      if (retries < this.MAX_RETRIES && (isTimeout || !window.navigator.onLine)) {
        // Exponential backoff
        await new Promise(resolve => setTimeout(resolve, Math.pow(2, retries) * 1000))
        return this.fetchWithRetry(url, options, retries + 1, customTimeoutMs)
      }
      throw err
    }
  }

  static async get<T>(endpoint: string): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`
    const response = await this.fetchWithRetry(url, {
      method: 'GET',
      headers: this.getHeaders(false, endpoint),
      credentials: 'include',
    })
    return this.handleResponse<T>(response)
  }

  static async post<T>(endpoint: string, data: any, requestId?: string): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`
    const headers = this.getHeaders(false, endpoint)
    headers['X-Request-ID'] = requestId ?? this.createRequestId()
    const response = await this.fetchWithRetry(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
      credentials: 'include',
    })
    return this.handleResponse<T>(response)
  }

  static async postWithRequestId<T>(endpoint: string, data: any, requestId: string): Promise<T> {
    return this.post<T>(endpoint, data, requestId)
  }

  static async postMultipart<T>(endpoint: string, formData: FormData, requestId?: string, timeoutMs?: number): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`
    const headers = this.getHeaders(true, endpoint)
    headers['X-Request-ID'] = requestId ?? this.createRequestId()
    const response = await this.fetchWithRetry(url, {
      method: 'POST',
      headers,
      body: formData,
      credentials: 'include',
    }, 0, timeoutMs)
    return this.handleResponse<T>(response)
  }

  static async postFormData<T>(endpoint: string, formData: FormData, requestId?: string): Promise<T> {
    return this.postMultipart<T>(endpoint, formData, requestId)
  }

  static async put<T>(endpoint: string, data: any): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`
    const headers = this.getHeaders(false, endpoint)
    headers['X-Request-ID'] = this.createRequestId()
    const response = await this.fetchWithRetry(url, {
      method: 'PUT',
      headers,
      body: JSON.stringify(data),
      credentials: 'include',
    })
    return this.handleResponse<T>(response)
  }

  static async delete(endpoint: string): Promise<void> {
    const url = `${API_BASE_URL}${endpoint}`
    const headers = this.getHeaders(false, endpoint)
    headers['X-Request-ID'] = this.createRequestId()
    const response = await this.fetchWithRetry(url, {
      method: 'DELETE',
      headers,
      credentials: 'include',
    })
    await this.handleResponse(response)
  }

  static async handleResponse<T>(response: Response): Promise<T> {
    if (response.status === 204) {
      return {} as T
    }

    const result = await response.json().catch(() => ({ 
      success: false, 
      data: null, 
      error: `Error ${response.status}: ${response.statusText}` 
    }))

    const isStandardFormat = result && typeof result === 'object' && 'success' in result
    const success = isStandardFormat ? result.success : response.ok
    const data = isStandardFormat ? result.data : result
    const error = isStandardFormat ? result.error : (result.detail || result.error || response.statusText)

    if (!success) {
      const errorMessage = typeof error === 'string' ? error : (error?.message || 'Unknown API error')

      if (typeof window !== 'undefined' && [401, 403, 500].includes(response.status)) {
        toast.error(`Error ${response.status}: ${errorMessage}`)
      }

      if ((response.status === 401 || response.status === 403) && typeof window !== 'undefined') {
        if (response.status === 401) {
          localStorage.removeItem('auth_token')
          if (!window.location.pathname.includes('/interview')) {
             window.location.href = '/'
          }
        }
      }
      
      // CRITICAL: Throw so that performMutation and other callers detect the failure
      throw new Error(errorMessage)
    }

    // Handled in the success case as well
    if (data == null) {
      return ({} as T)
    }

    return data as T
  }
}
