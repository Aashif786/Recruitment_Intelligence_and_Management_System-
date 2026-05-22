'use client'

import React, { useState } from "react"
import { useAuth } from '@/app/dashboard/lib/auth-context'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { motion, AnimatePresence } from 'framer-motion'
import { Button } from '@/components/ui/button'
import {
  Zap, Mail, Lock, User, Check, ArrowRight,
  Loader2, Brain, Cpu, Globe, LucideIcon
} from 'lucide-react'
import { cn } from '@/app/dashboard/lib/utils'
import useSWR from 'swr'
import { APIClient } from '@/app/dashboard/lib/api-client'

export default function RegisterPage() {
  const router = useRouter()
  const { register, isLoading } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [agreedToTerms, setAgreedToTerms] = useState(false)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const { data: settings } = useSWR('/api/settings', (url) => APIClient.get(url)) as { data: any }
  const companyLogo = settings?.company_logo_url || "/calrims/logo-dark.png"
  const companyName = settings?.company_name || "RIMS"

  const passwordLength = password.length >= 8
  const passwordUppercase = /[A-Z]/.test(password)
  const passwordNumber = /[0-9]/.test(password)
  const passwordSpecial = /[^A-Za-z0-9]/.test(password)
  const passwordCriteriaCount = [passwordLength, passwordUppercase, passwordNumber, passwordSpecial].filter(Boolean).length

  let passwordStrength = 'Weak'
  let passwordStrengthColor = 'bg-destructive'
  if (passwordCriteriaCount === 4) {
    passwordStrength = 'Strong'
    passwordStrengthColor = 'bg-emerald-500'
  } else if (passwordCriteriaCount >= 2) {
    passwordStrength = 'Fair'
    passwordStrengthColor = 'bg-yellow-500'
  }
  if (password.length === 0) passwordStrength = ''

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    const emailRegex = /^(?!\d+@)(?![^@]*\.\.)(?!^\.)[A-Za-z0-9_\-+]+(?:\.[A-Za-z0-9_\-+]+)*@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}$/;
    if (!emailRegex.test(email)) {
      setError("Enter valid email");
      return;
    }

    if (!agreedToTerms) {
      setError('You must agree to the terms and conditions')
      return
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    if (passwordCriteriaCount < 4) {
      setError('Password does not meet all requirements')
      return
    }

    setIsSubmitting(true)

    try {
      await register(email, password, fullName)
      router.push(`/auth/verify?email=${encodeURIComponent(email)}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="h-[calc(100vh-4rem)] flex-1 w-full flex flex-col lg:flex-row bg-background selection:bg-primary/20 relative overflow-hidden">

      {/* LEFT COLUMN: Hero Imagery (Hidden on Mobile) */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-slate-950">
        {/* The second generated AI/HR image */}
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: 'url(/calrims/auth-bg-2.png)' }}
        />
        {/* Heavy gradient overlay to make text readable and blend edges */}
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/40 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-r from-slate-950/60 to-transparent" />

        {/* Content overlaid on image (Top Left Corner) */}
        <div className="absolute top-10 left-12 z-20">
          <div className="flex flex-col gap-5 w-full max-w-[55rem]">
            <h2 className="text-4xl lg:text-[2.75rem] font-light uppercase tracking-[0.15em] leading-[1.3] text-white/90">
              Recruitment Intelligence & <br /> Management System
            </h2>
            <div className="inline-flex w-max items-center justify-center rounded-lg border border-white/10 bg-slate-950/40 px-4 py-2 backdrop-blur-md">
              <span className="text-xs font-bold tracking-[0.2em] uppercase text-white/90">
                BY {companyName.toUpperCase()}
              </span>
            </div>
          </div>
        </div>

        {/* Content overlaid on image (Bottom) */}
        <div className="relative z-10 p-12 mt-auto flex flex-col justify-end h-full w-full max-w-2xl text-slate-100">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="space-y-6"
          >
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/20 border border-emerald-500/30 backdrop-blur-md">
              <Globe className="h-4 w-4 text-emerald-400" />
              <span className="text-sm font-semibold tracking-wide uppercase text-emerald-100">Global Talent Network</span>
            </div>

            <h1 className="text-4xl xl:text-5xl font-extrabold leading-tight tracking-tight text-white mb-4">
              Build your legacy.
            </h1>

            <p className="text-lg xl:text-xl text-slate-300 max-w-lg mb-8 leading-relaxed">
              Join thousands of forward-thinking teams using AI to find, evaluate, and hire top-tier talent.
            </p>

            <div className="grid grid-cols-2 gap-6 pt-6 border-t border-slate-700/50">
              <div className="flex items-start gap-4">
                <div className="mt-1 bg-indigo-500/20 p-2 rounded-lg text-indigo-400">
                  <Cpu className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-bold text-white">Automated Pipelines</h4>
                  <p className="text-sm text-slate-400">Scale without the overhead</p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <div className="mt-1 bg-cyan-500/20 p-2 rounded-lg text-cyan-400">
                  <Brain className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-bold text-white">Live AI Interviews</h4>
                  <p className="text-sm text-slate-400">Deep technical screening</p>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* RIGHT COLUMN: Interactive Form */}
      <div className="w-full lg:w-1/2 flex flex-col items-center justify-center p-8 sm:p-12 lg:p-16 xl:p-12 relative overflow-y-auto lg:min-h-0 bg-background/95">
        
        {/* Subtle background decoration for right side */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden z-0">
           <div className="absolute top-[0%] right-[0%] w-[300px] h-[300px] bg-primary/5 rounded-full blur-[100px]" />
           <div className="absolute bottom-[0%] left-[0%] w-[300px] h-[300px] bg-emerald-500/5 rounded-full blur-[100px]" />
        </div>

        <div className="w-full max-w-md relative z-10 py-10">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            {/* Logo for mobile only */}
            <div className="flex items-center gap-3 lg:hidden mb-8">
               <img src={companyLogo} alt="Logo" className="h-8 w-auto object-contain max-w-[120px]" />
               <span className="text-xl font-bold tracking-tight">{companyName}</span>
            </div>

            <div className="space-y-2 mb-8">
              <h2 className="text-3xl font-extrabold tracking-tight text-foreground">Create HR Account</h2>
              <p className="text-muted-foreground">Register an HR account. After verification, a Super Admin must approve your access.</p>
            </div>
          </motion.div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                  animate={{ opacity: 1, height: 'auto', marginBottom: 20 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                  className="overflow-hidden"
                >
                  <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-xl text-destructive text-sm font-semibold flex items-center gap-3">
                    <div className="w-1.5 h-1.5 rounded-full bg-destructive animate-pulse shrink-0" />
                    {error}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.1 }}>
              <InputField
                id="fullName" label="Full Name" type="text"
                placeholder="Eleanor Shellstrop" value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                icon={User} disabled={isSubmitting}
              />
            </motion.div>

            <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.15 }}>
              <InputField
                id="email" label="Work Email" type="email"
                placeholder="eleanor@company.com" value={email}
                onChange={(e) => setEmail(e.target.value)}
                icon={Mail} disabled={isSubmitting}
              />
            </motion.div>

            <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.2 }}>
              <div className="grid grid-cols-2 gap-4">
                <InputField
                  id="password" label="Password" type="password"
                  placeholder="••••••••" value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  icon={Lock} disabled={isSubmitting}
                  autoComplete="new-password"
                />
                <InputField
                  id="confirmPassword" label="Confirm Password" type="password"
                  placeholder="••••••••" value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  icon={Check} disabled={isSubmitting}
                  autoComplete="new-password"
                />
              </div>
              
              {/* Password Strength Meter */}
              {password.length > 0 && (
                <div className="mt-3 space-y-2 pl-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Password Strength</span>
                    <span className={cn("text-xs font-bold", passwordStrength === 'Strong' ? 'text-emerald-500' : passwordStrength === 'Fair' ? 'text-yellow-500' : 'text-destructive')}>{passwordStrength}</span>
                  </div>
                  <div className="flex gap-1 h-1.5 w-full">
                    <div className={cn("h-full flex-1 rounded-full", passwordCriteriaCount >= 1 ? passwordStrengthColor : 'bg-muted')} />
                    <div className={cn("h-full flex-1 rounded-full", passwordCriteriaCount >= 2 && passwordCriteriaCount < 4 ? 'bg-yellow-500' : passwordCriteriaCount === 4 ? 'bg-emerald-500' : 'bg-muted')} />
                    <div className={cn("h-full flex-1 rounded-full", passwordCriteriaCount >= 3 && passwordCriteriaCount < 4 ? 'bg-yellow-500' : passwordCriteriaCount === 4 ? 'bg-emerald-500' : 'bg-muted')} />
                    <div className={cn("h-full flex-1 rounded-full", passwordCriteriaCount === 4 ? 'bg-emerald-500' : 'bg-muted')} />
                  </div>
                  <div className="grid grid-cols-2 gap-2 mt-2 pt-1">
                    <div className="flex items-center gap-1.5">
                      <Check className={cn("w-3 h-3", passwordLength ? "text-emerald-500" : "text-muted-foreground")} />
                      <span className={cn("text-xs", passwordLength ? "text-emerald-500" : "text-muted-foreground")}>8+ characters</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Check className={cn("w-3 h-3", passwordUppercase ? "text-emerald-500" : "text-muted-foreground")} />
                      <span className={cn("text-xs", passwordUppercase ? "text-emerald-500" : "text-muted-foreground")}>1 uppercase</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Check className={cn("w-3 h-3", passwordNumber ? "text-emerald-500" : "text-muted-foreground")} />
                      <span className={cn("text-xs", passwordNumber ? "text-emerald-500" : "text-muted-foreground")}>1 number</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Check className={cn("w-3 h-3", passwordSpecial ? "text-emerald-500" : "text-muted-foreground")} />
                      <span className={cn("text-xs", passwordSpecial ? "text-emerald-500" : "text-muted-foreground")}>1 special char</span>
                    </div>
                  </div>
                </div>
              )}
            </motion.div>

            <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.3 }} className="pt-2">
              <div className="flex items-start gap-3 px-1">
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={agreedToTerms}
                  aria-label="Agree to Terms of Service and Privacy Policy"
                  id="terms-checkbox"
                  onClick={() => setAgreedToTerms(!agreedToTerms)}
                  className={cn(
                    "mt-0.5 w-5 h-5 rounded-md border-2 transition-all flex items-center justify-center shrink-0",
                    agreedToTerms ? "bg-primary border-primary" : "bg-transparent border-border hover:border-primary/50"
                  )}
                >
                  {agreedToTerms && <Check className="w-3.5 h-3.5 text-primary-foreground stroke-[4px]" />}
                </button>
                <label htmlFor="terms-checkbox" className="text-sm text-muted-foreground font-medium leading-tight cursor-pointer">
                  I agree to the <Link href="/terms" className="text-foreground hover:text-primary font-bold transition-colors">Terms of Service</Link> and <Link href="/privacy" className="text-foreground hover:text-primary font-bold transition-colors">Privacy Policy</Link>.
                </label>
              </div>
            </motion.div>

            <motion.div 
               initial={{ opacity: 0, y: 20 }}
               animate={{ opacity: 1, y: 0 }}
               transition={{ duration: 0.5, delay: 0.35 }}
               className="pt-4"
            >
              <Button
                type="submit"
                disabled={isSubmitting || isLoading || passwordCriteriaCount < 4 || !agreedToTerms}
                className="w-full h-12 bg-foreground hover:bg-foreground/90 text-background font-bold rounded-xl shadow-lg transition-all active:scale-[0.98] flex items-center justify-center gap-2 group"
              >
                {isSubmitting ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <>
                    <span>Create Account</span>
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                  </>
                )}
              </Button>
            </motion.div>
          </form>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.45 }}
            className="mt-8 text-center"
          >
            <p className="text-sm font-medium text-muted-foreground">
              Already have an account?{' '}
              <Link href="/auth/login" className="text-foreground font-bold hover:text-primary transition-colors underline underline-offset-4">
                Sign In
              </Link>
            </p>
          </motion.div>
        </div>
      </div>
    </div>
  )
}

function InputField({ id, label, type, placeholder, value, onChange, icon: Icon, disabled, autoComplete }: {
  id: string,
  label: string,
  type: string,
  placeholder: string,
  value: string,
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void,
  icon: LucideIcon,
  disabled: boolean,
  autoComplete?: string
}) {
  return (
    <div className="group space-y-1.5">
      <label htmlFor={id} className="text-xs font-bold text-muted-foreground uppercase tracking-wider px-1 inline-block group-focus-within:text-primary transition-colors">
        {label}
      </label>
      <div className="relative">
        <div className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground/70 group-focus-within:text-primary transition-colors">
          <Icon className="h-5 w-5" />
        </div>
        <input
          id={id}
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete={autoComplete}
          required
          className={cn(
            "w-full h-12 pl-12 pr-4 bg-muted/30 border border-border/50 rounded-xl outline-none transition-all duration-300",
            "focus:border-primary focus:ring-4 focus:ring-primary/10 focus:bg-background",
            "placeholder:text-muted-foreground/40 text-foreground font-medium shadow-sm",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        />
      </div>
    </div>
  )
}
