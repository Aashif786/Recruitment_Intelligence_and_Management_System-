"use client";

import { useAuth } from "@/app/dashboard/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Star,
  Users,
  Zap,
} from "lucide-react";
import { ToggleTheme } from "@/components/lightswind/toggle-theme";
import { FloatingHeroShapes } from "@/components/floating-hero-shapes";
import { InteractiveFeatureBg } from "@/components/interactive-feature-bg";
import { Libre_Franklin } from "next/font/google";

const franklin = Libre_Franklin({ subsets: ["latin"] });

export default function Home() {
  const { isAuthenticated, user, isLoading } = useAuth();
  const router = useRouter();
  const [showError, setShowError] = useState(false);

  useEffect(() => {
    let timeout: NodeJS.Timeout;
    if (isLoading) {
      timeout = setTimeout(() => {
        setShowError(true);
      }, 5000);
    }
    return () => clearTimeout(timeout);
  }, [isLoading]);



  if (showError) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-950 text-slate-100 relative overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(59,130,246,0.1)_1px,transparent_1px),linear-gradient(90deg,rgba(59,130,246,0.1)_1px,transparent_1px)] bg-[size:40px_40px] opacity-20" />
        <div className="relative z-10 flex flex-col items-center max-w-md text-center p-8 bg-slate-900/50 border border-slate-800 rounded-2xl backdrop-blur-sm">
          <Zap className="w-12 h-12 text-destructive mb-6" />
          <h2 className="text-2xl font-bold mb-3">Connection Timeout</h2>
          <p className="text-lg text-slate-400 mb-8">Something went wrong. Please refresh and try again.</p>
          <Button onClick={() => window.location.reload()} size="lg" className="h-12 px-8 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold w-full">
            Reload Page
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="relative min-h-screen font-sans selection:bg-primary/10 selection:text-primary-foreground overflow-x-hidden bg-[#dde9f8]"
    >
      {/* Hero Section */}
      <div
        className="relative min-h-screen flex items-center overflow-hidden bg-[#dde9f8]"
      >
        {/* ── Background pattern at 50% opacity ── */}
        <div
          aria-hidden="true"
          className="absolute inset-0 z-0 pointer-events-none"
          style={{ opacity: 0.5 }}
        >
          {/* Grid lines */}
          <div
            className="absolute inset-0"
            style={{
              backgroundImage:
                "linear-gradient(rgba(59,130,246,0.18) 1px, transparent 1px), linear-gradient(90deg, rgba(59,130,246,0.18) 1px, transparent 1px)",
              backgroundSize: "60px 60px",
            }}
          />

          {/* Circuit-board trace layer */}
          <div className="absolute inset-0 overflow-hidden">
            <svg
              width="100%"
              height="100%"
              viewBox="0 0 1440 800"
              preserveAspectRatio="xMidYMid slice"
              xmlns="http://www.w3.org/2000/svg"
              style={{ position: "absolute", inset: 0 }}
            >
              <defs>
                <filter id="glow">
                  <feGaussianBlur stdDeviation="2.5" result="coloredBlur" />
                  <feMerge>
                    <feMergeNode in="coloredBlur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
                <style>{`
                .trace { fill: none; stroke: rgba(59,130,246,0.55); stroke-width: 1.2; filter: url(#glow); }
                .node  { fill: rgba(59,130,246,0.8); filter: url(#glow); }
                @keyframes tracePulse {
                  0%,100% { opacity: 0.45; } 50% { opacity: 0.9; }
                }
                .trace { animation: tracePulse 4s ease-in-out infinite; }
                .node  { animation: tracePulse 4s ease-in-out infinite 0.5s; }
              `}</style>
              </defs>

              {/* Trace group 1 – upper mid */}
              <polyline
                className="trace"
                points="80,120 280,120 320,160 620,160 660,120 900,120"
              />
              <circle className="node" cx="280" cy="120" r="3.5" />
              <circle className="node" cx="620" cy="160" r="3.5" />
              <circle className="node" cx="900" cy="120" r="3.5" />

              {/* Trace group 2 – upper */}
              <polyline
                className="trace"
                points="0,200 160,200 200,240 480,240 520,200 760,200 800,240 1100,240 1140,200 1440,200"
              />
              <circle className="node" cx="160" cy="200" r="3.5" />
              <circle className="node" cx="520" cy="200" r="3.5" />
              <circle className="node" cx="800" cy="240" r="3.5" />
              <circle className="node" cx="1140" cy="200" r="3.5" />

              {/* Trace group 3 – center */}
              <polyline
                className="trace"
                points="0,340 200,340 240,380 560,380 600,340 840,340 880,380 1200,380 1240,340 1440,340"
              />
              <circle className="node" cx="200" cy="340" r="3.5" />
              <circle className="node" cx="560" cy="380" r="3.5" />
              <circle className="node" cx="880" cy="380" r="3.5" />
              <circle className="node" cx="1240" cy="340" r="3.5" />

              {/* Trace group 4 – lower mid */}
              <polyline
                className="trace"
                points="100,480 360,480 400,520 700,520 740,480 1000,480 1040,520 1340,520"
              />
              <circle className="node" cx="360" cy="480" r="3.5" />
              <circle className="node" cx="700" cy="520" r="3.5" />
              <circle className="node" cx="1040" cy="520" r="3.5" />

              {/* Trace group 5 – lower */}
              <polyline
                className="trace"
                points="0,620 220,620 260,580 500,580 540,620 780,620 820,580 1060,580 1100,620 1440,620"
              />
              <circle className="node" cx="220" cy="620" r="3.5" />
              <circle className="node" cx="540" cy="620" r="3.5" />
              <circle className="node" cx="820" cy="580" r="3.5" />
              <circle className="node" cx="1100" cy="620" r="3.5" />

              {/* Vertical connectors */}
              <line className="trace" x1="320" y1="120" x2="320" y2="200" />
              <line className="trace" x1="660" y1="120" x2="660" y2="200" />
              <line className="trace" x1="240" y1="240" x2="240" y2="340" />
              <line className="trace" x1="600" y1="340" x2="600" y2="380" />
              <line className="trace" x1="880" y1="340" x2="880" y2="380" />
              <line className="trace" x1="400" y1="480" x2="400" y2="520" />
              <line className="trace" x1="740" y1="480" x2="740" y2="520" />
            </svg>
          </div>
          {/* end circuit layer */}
        </div>
        {/* end 50% opacity wrapper */}

        {/* ── Floating geometric shapes (boosted for dark bg) ── */}
        <div
          aria-hidden="true"
          className="absolute inset-0 z-0 pointer-events-none"
        >
          {/* Circle 1 – top-left */}
          <div
            style={{
              position: "absolute",
              top: "8%",
              left: "4%",
              width: 80,
              height: 80,
              borderRadius: "50%",
              border: "2px solid rgba(59,130,246,0.30)",
              background: "rgba(59,130,246,0.06)",
              animation: "driftA 3s ease-in-out infinite",
            }}
          />
          {/* Square – top-center */}
          <div
            style={{
              position: "absolute",
              top: "5%",
              left: "42%",
              width: 52,
              height: 52,
              border: "2px solid rgba(99,102,241,0.30)",
              background: "rgba(99,102,241,0.06)",
              animation: "driftB 2.5s ease-in-out infinite",
            }}
          />
          {/* Rectangle – mid-left */}
          <div
            style={{
              position: "absolute",
              top: "40%",
              left: "2%",
              width: 110,
              height: 55,
              border: "2px solid rgba(59,130,246,0.25)",
              background: "rgba(59,130,246,0.05)",
              borderRadius: 6,
              animation: "driftC 4s ease-in-out infinite",
            }}
          />
          {/* Triangle – mid-center */}
          <div
            style={{
              position: "absolute",
              top: "30%",
              left: "35%",
              width: 70,
              height: 70,
              background: "rgba(99,102,241,0.10)",
              clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)",
              animation: "driftA 2.8s ease-in-out infinite 0.4s",
            }}
          />
          {/* Circle 2 – bottom-left */}
          <div
            style={{
              position: "absolute",
              bottom: "10%",
              left: "18%",
              width: 48,
              height: 48,
              borderRadius: "50%",
              border: "2px solid rgba(59,130,246,0.22)",
              background: "rgba(59,130,246,0.05)",
              animation: "driftB 2.2s ease-in-out infinite 0.2s",
            }}
          />
          {/* Square 2 – bottom-center */}
          <div
            style={{
              position: "absolute",
              bottom: "8%",
              left: "50%",
              width: 40,
              height: 40,
              border: "2px solid rgba(99,102,241,0.25)",
              background: "rgba(99,102,241,0.06)",
              animation: "driftC 3.5s ease-in-out infinite 0.8s",
            }}
          />
          {/* Triangle 2 – top-right */}
          <div
            style={{
              position: "absolute",
              top: "15%",
              left: "62%",
              width: 56,
              height: 56,
              background: "rgba(59,130,246,0.09)",
              clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)",
              animation: "driftA 3.2s ease-in-out infinite 1s",
            }}
          />
          {/* Rectangle 2 – top-right corner */}
          <div
            style={{
              position: "absolute",
              top: "3%",
              right: "3%",
              width: 90,
              height: 40,
              border: "2px solid rgba(99,102,241,0.22)",
              background: "rgba(99,102,241,0.05)",
              borderRadius: 4,
              animation: "driftB 2.6s ease-in-out infinite 0.6s",
            }}
          />
        </div>

        {/* ── CSS keyframes ── */}
        <style>{`
          @keyframes driftA {
            0%,100% { transform: translateX(0px)    rotate(0deg);  }
            50%      { transform: translateX(130px)  rotate(6deg);  }
          }
          @keyframes driftB {
            0%,100% { transform: translateX(0px)    rotate(0deg);  }
            50%      { transform: translateX(-140px) rotate(-8deg); }
          }
          @keyframes driftC {
            0%,100% { transform: translateX(0px)    rotate(0deg);  }
            33%      { transform: translateX(110px)  rotate(5deg);  }
            66%      { transform: translateX(-110px) rotate(-5deg); }
          }
          @keyframes pulseRing {
            0%   { transform: scale(0.5); opacity: 0.55; }
            100% { transform: scale(2.4); opacity: 0; }
          }
          @keyframes floatParticle {
            0%,100% { transform: translateY(0px) translateX(0px); opacity: 0.7; }
            33%      { transform: translateY(-22px) translateX(12px); opacity: 1; }
            66%      { transform: translateY(-10px) translateX(-14px); opacity: 0.5; }
          }
          @keyframes blobPulse {
            0%,100% { transform: scale(1);    opacity: 0.18; }
            50%      { transform: scale(1.12); opacity: 0.28; }
          }
          @keyframes barGrow {
            from { transform: scaleY(0); opacity: 0; }
            to   { transform: scaleY(1); opacity: 1; }
          }
          /* Hero heading hover effects — 3D tilt */
          .hero-text-block {
            transition: transform 0.45s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.45s ease;
            transform-origin: center center;
            transform-style: preserve-3d;
            perspective: 800px;
            will-change: transform;
          }
          .hero-text-block:hover {
            transform: perspective(800px) rotateY(8deg) rotateX(-5deg) translateX(-12px) translateY(-18px);
            box-shadow: 12px 12px 40px rgba(59,130,246,0.15);
          }
          .glass-feature-card {
            background: rgba(255, 255, 255, 0.35);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border: 1px solid rgba(255, 255, 255, 0.55);
            transition: transform 0.45s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.45s ease, border-color 0.45s ease, background 0.45s ease;
            transform-origin: center center;
            transform-style: preserve-3d;
            perspective: 1000px;
            will-change: transform;
            box-shadow: 0 8px 32px rgba(59, 130, 246, 0.10), inset 0 1px 0 rgba(255,255,255,0.5);
          }
          .dark .glass-feature-card {
            background: rgba(15, 37, 71, 0.25);
            border: 1px solid rgba(255, 255, 255, 0.12);
          }
          .glass-feature-card:hover {
            transform: perspective(1000px) rotateY(6deg) rotateX(-5deg) translateY(-10px) scale(1.02);
            background: rgba(255, 255, 255, 0.50);
            box-shadow: 20px 20px 50px rgba(59, 130, 246, 0.18), inset 0 1px 0 rgba(255,255,255,0.7);
            border-color: rgba(255, 255, 255, 0.85);
          }
          .glass-feature-card.tilt-up:hover {
            transform: perspective(1000px) rotateX(8deg) rotateY(0deg) translateY(-10px) scale(1.02);
          }
          .hero-title-stroke {
            transition: color 0.35s ease;
          }
          @keyframes globeSlowPan {
            0% { transform: scale(1) translate(0, 0); }
            50% { transform: scale(1.05) translate(-1%, 1%); }
            100% { transform: scale(1) translate(0, 0); }
          }
          @keyframes starPulse {
            0%, 100% { opacity: 0.2; transform: scale(0.8); }
            50% { opacity: 0.8; transform: scale(1.2); }
          }
          @keyframes gridMove {
            0% { background-position: 0 0; }
            100% { background-position: 60px 60px; }
          }
          @keyframes flowPathAnim {
            from { stroke-dashoffset: 1000; }
            to   { stroke-dashoffset: 0; }
          }
          .trace-flow-path {
            stroke-dasharray: 20 20;
            animation: flowPathAnim 12s linear infinite;
            filter: drop-shadow(0 0 8px rgba(59,130,246,1));
            opacity: 0.85;
          }
          .interactive-grid {
            opacity: 0.15;
            transition: opacity 0.4s ease;
            animation: gridMove 15s linear infinite;
          }
          .features-section:hover .interactive-grid {
            opacity: 0.4;
          }
          @keyframes dustDrift1 {
            0% { transform: translate(0px, 0px); opacity: 0; }
            20% { opacity: 0.6; }
            80% { opacity: 0.6; }
            100% { transform: translate(80px, -150px); opacity: 0; }
          }
          @keyframes dustDrift2 {
            0% { transform: translate(0px, 0px); opacity: 0; }
            20% { opacity: 0.4; }
            80% { opacity: 0.4; }
            100% { transform: translate(-60px, -120px); opacity: 0; }
          }
          @keyframes dustDrift3 {
            0% { transform: translate(0px, 0px); opacity: 0; }
            20% { opacity: 0.5; }
            80% { opacity: 0.5; }
            100% { transform: translate(40px, -180px); opacity: 0; }
          }
          @keyframes binaryFall {
            0% { transform: translateY(-50%); }
            100% { transform: translateY(0%); }
          }
        `}</style>

        {/* ── Right-side animated fill ── */}
        <div
          aria-hidden="true"
          className="absolute inset-0 z-0 pointer-events-none overflow-hidden"
        >
          {/* Soft radial glow blob */}
          <div
            style={{
              position: "absolute",
              right: "5%",
              top: "15%",
              width: 460,
              height: 460,
              borderRadius: "50%",
              background:
                "radial-gradient(circle, rgba(99,155,246,0.32) 0%, rgba(99,155,246,0) 70%)",
              animation: "blobPulse 5s ease-in-out infinite",
            }}
          />

          {/* Pulse ring 1 */}
          <div
            style={{
              position: "absolute",
              right: "22%",
              top: "28%",
              width: 160,
              height: 160,
              borderRadius: "50%",
              border: "2px solid rgba(59,130,246,0.45)",
              animation: "pulseRing 3s ease-out infinite",
            }}
          />
          {/* Pulse ring 2 – staggered */}
          <div
            style={{
              position: "absolute",
              right: "22%",
              top: "28%",
              width: 160,
              height: 160,
              borderRadius: "50%",
              border: "2px solid rgba(59,130,246,0.38)",
              animation: "pulseRing 3s ease-out infinite 1s",
            }}
          />
          {/* Pulse ring 3 – staggered */}
          <div
            style={{
              position: "absolute",
              right: "22%",
              top: "28%",
              width: 160,
              height: 160,
              borderRadius: "50%",
              border: "2px solid rgba(59,130,246,0.28)",
              animation: "pulseRing 3s ease-out infinite 2s",
            }}
          />

          {/* Floating particles (small dots) */}
          {[
            {
              right: "8%",
              top: "12%",
              delay: "0s",
              size: 6,
              color: "rgba(59,130,246,0.6)",
            },
            {
              right: "15%",
              top: "55%",
              delay: "0.6s",
              size: 5,
              color: "rgba(99,102,241,0.55)",
            },
            {
              right: "28%",
              top: "70%",
              delay: "1.2s",
              size: 7,
              color: "rgba(59,130,246,0.5)",
            },
            {
              right: "38%",
              top: "20%",
              delay: "0.3s",
              size: 5,
              color: "rgba(99,102,241,0.6)",
            },
            {
              right: "12%",
              top: "80%",
              delay: "1.8s",
              size: 4,
              color: "rgba(59,130,246,0.45)",
            },
            {
              right: "32%",
              top: "88%",
              delay: "0.9s",
              size: 6,
              color: "rgba(59,130,246,0.4)",
            },
            {
              right: "6%",
              top: "45%",
              delay: "1.5s",
              size: 5,
              color: "rgba(99,102,241,0.5)",
            },
            {
              right: "20%",
              top: "35%",
              delay: "0.4s",
              size: 4,
              color: "rgba(59,130,246,0.55)",
            },
          ].map((p, i) => (
            <div
              key={i}
              style={{
                position: "absolute",
                right: p.right,
                top: p.top,
                width: p.size,
                height: p.size,
                borderRadius: "50%",
                background: p.color,
                boxShadow: `0 0 6px 2px ${p.color}`,
                animation: `floatParticle 4s ease-in-out infinite ${p.delay}`,
              }}
            />
          ))}
        </div>

        {/* ── Bar chart decoration — bottom-left ── */}
        <div
          aria-hidden="true"
          className="absolute bottom-0 left-[50px] z-[2] pointer-events-none flex items-end gap-8 pl-6"
        >
          <div
            style={{
              width: 65,
              height: 520,
              background: "#0a1a3c",
              borderRadius: "6px 6px 0 0",
              animation: "barGrow 0.9s ease-out both",
              animationDelay: "0s",
            }}
          />
          <div
            style={{
              width: 65,
              height: 360,
              background: "#0a1a3c",
              borderRadius: "6px 6px 0 0",
              animation: "barGrow 0.9s ease-out both",
              animationDelay: "0.15s",
            }}
          />
          <div
            style={{
              width: 65,
              height: 220,
              background: "#0a1a3c",
              borderRadius: "6px 6px 0 0",
              animation: "barGrow 0.9s ease-out both",
              animationDelay: "0.3s",
            }}
          />
        </div>
        {/* ── Person image — z-[1] ── */}
        <div className="absolute inset-0 z-[1] pointer-events-none">
          <img
            src="/calrims/1person.png"
            alt=""
            className="absolute right-0 bottom-0 h-auto max-h-[75%] w-auto object-contain object-right-bottom select-none"
            aria-hidden="true"
          />
        </div>

        {/* ── Hero text — z-10 ── */}
        <div className="max-w-7xl mx-auto px-6 relative z-10">
          <div className="max-w-2xl" style={{ marginTop: "-120px" }}>
            <div
              className="hero-text-block mb-8 space-y-4 text-center"
              style={{ marginLeft: "-280px", maxWidth: "56rem" }}
            >
              {/* Badge */}
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/5 border border-primary/20 text-primary text-xs font-semibold uppercase tracking-[0.18em] mb-2">
                <Star className="h-3 w-3 fill-primary" />
                AI-DRIVEN RECRUITMENT SYSTEM
              </div>

              <h1 className="text-5xl md:text-7xl font-semibold tracking-tight leading-tight">
                <span
                  className="hero-title-stroke whitespace-nowrap text-slate-950"
                >
                  Hire with the same precision
                </span>
                <span className="block text-primary">
                  you use to build products.
                </span>
              </h1>
              <p className="text-xl md:text-2xl text-slate-600 max-w-xl mx-auto">
                Our Product runs structured, bias-free interviews, scores
                skills, and turns every conversation into decision-ready
                analytics.
              </p>
            </div>

            {/* ── Buttons — original inline position ── */}
            {isLoading ? (
              <div
                className="flex flex-col sm:flex-row gap-4 items-center justify-center mt-6"
                style={{ marginLeft: "-280px" }}
              >
                <div className="h-12 w-[220px] bg-slate-800/50 rounded-md animate-pulse border border-slate-700/50"></div>
                <div className="h-12 w-[160px] bg-slate-800/50 rounded-md animate-pulse border border-slate-700/50"></div>
              </div>
            ) : (
              <div
                className="flex flex-col sm:flex-row gap-4 items-center justify-center mt-6"
                style={{ marginLeft: "-280px" }}
              >
                <Link href="/auth/login?role=hr">
                  <Button size="lg" className="h-12 px-7 cursor-pointer">
                    Start hiring in minutes
                    <ArrowRight className="ml-2 h-5 w-5" />
                  </Button>
                </Link>
                <Link href="/jobs">
                  <Button
                    size="lg"
                    variant="outline"
                    className="h-12 px-7 border-border/70 bg-background/70 cursor-pointer"
                  >
                    Browse open roles
                  </Button>
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Features Grid - Alternating Layout */}
      <section className="features-section py-20 relative z-10 overflow-hidden">
        {/* ── Section Background ── */}
        <div className="absolute inset-0 z-[-1] pointer-events-none overflow-hidden">
          <div
            className="w-full h-full"
            style={{
              backgroundImage: "url(/calrims/GLOBE.jpg)",
              backgroundSize: "cover",
              backgroundPosition: "center",
              opacity: 0.5,
              animation: "globeSlowPan 30s ease-in-out infinite",
            }}
          />
        </div>

        {/* ── Soft blend/blur from hero section ── */}
        <div className="absolute top-0 inset-x-0 h-48 bg-gradient-to-b from-[#dde9f8] via-[#dde9f8]/60 to-transparent z-0 pointer-events-none" />

        {/* ── Floating Dust Particles ── */}
        <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
          {Array.from({ length: 25 }).map((_, i) => {
            // Deterministic distribution based on index (avoids hydration mismatch)
            const seed = (i * 7 + 3) % 25;
            const size = (seed % 3) + 1;
            const top = ((seed * 17 + i * 13) % 100) + "%";
            const left = ((seed * 23 + i * 7) % 100) + "%";
            const duration = (seed % 15) + 15 + "s";
            const delay = (i * 0.8) + "s";
            const animType =
              i % 3 === 0
                ? "dustDrift1"
                : i % 2 === 0
                  ? "dustDrift2"
                  : "dustDrift3";

            return (
              <div
                key={`dust-${i}`}
                style={{
                  position: "absolute",
                  top: top,
                  left: left,
                  width: size,
                  height: size,
                  backgroundColor: "#ffffff",
                  borderRadius: "50%",
                  boxShadow: "0 0 4px 1px rgba(255,255,255,0.4)",
                  animation: `${animType} ${duration} linear infinite ${delay}`,
                  opacity: 0,
                }}
              />
            );
          })}
        </div>

        {/* ── Interactive Grid Background ── */}
        <div
          className="interactive-grid absolute inset-0 z-0 pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(rgba(59,130,246,0.2) 1px, transparent 1px), linear-gradient(90deg, rgba(59,130,246,0.2) 1px, transparent 1px)",
            backgroundSize: "60px 60px",
          }}
        />

        {/* ── Glowing Flow Path (S-Curve) ── */}
        <div className="absolute inset-0 z-0 pointer-events-none hidden md:block">
          <svg
            className="w-full h-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
          >
            <path
              d="M 85,0 L 85,32 L 15,32 L 15,68 L 85,68 L 85,100"
              fill="none"
              stroke="#3b82f6"
              strokeWidth="3"
              vectorEffect="non-scaling-stroke"
              className="trace-flow-path"
              strokeLinejoin="bevel"
            />
          </svg>
        </div>

        {/* ── Floating Background Orbs & Stars ── */}
        <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
          {/* Big soft orbs */}
          <div className="absolute top-[10%] left-[10%] w-[350px] h-[350px] bg-blue-500/5 rounded-full" />
          <div className="absolute top-[40%] right-[5%] w-[450px] h-[450px] bg-indigo-500/5 rounded-full" />
          <div className="absolute bottom-[5%] left-[15%] w-[400px] h-[400px] bg-sky-400/5 rounded-full" />

          {/* Scattered Pulsing Stars */}
          {[
            { top: "15%", left: "80%", size: 4, delay: "0s" },
            { top: "25%", left: "15%", size: 3, delay: "1s" },
            { top: "45%", left: "90%", size: 5, delay: "2s" },
            { top: "65%", left: "10%", size: 4, delay: "0.5s" },
            { top: "75%", left: "85%", size: 3, delay: "1.5s" },
            { top: "85%", left: "25%", size: 5, delay: "2.5s" },
            { top: "35%", left: "50%", size: 4, delay: "0.8s" },
            { top: "90%", left: "60%", size: 3, delay: "1.8s" },
          ].map((star, i) => (
            <div
              key={i}
              style={{
                position: "absolute",
                top: star.top,
                left: star.left,
                width: star.size,
                height: star.size,
                backgroundColor: "#dde9f8",
                borderRadius: "50%",
                boxShadow: "0 0 10px 2px rgba(59,130,246,0.6)",
                animation: `starPulse 4s ease-in-out infinite ${star.delay}`,
              }}
            />
          ))}
        </div>

        {/* ── Left Binary Columns ── */}
        <BinaryColumn
          left="3%"
          delay="0s"
          duration="25s"
          opacity={0.3}
          text={b1}
        />
        <BinaryColumn
          left="6%"
          delay="-7s"
          duration="30s"
          opacity={0.15}
          text={b2}
        />
        <BinaryColumn
          left="9%"
          delay="-14s"
          duration="22s"
          opacity={0.2}
          text={b3}
        />

        {/* ── Right Binary Columns ── */}
        <BinaryColumn
          right="9%"
          delay="-4s"
          duration="28s"
          opacity={0.2}
          text={b2}
        />
        <BinaryColumn
          right="6%"
          delay="-10s"
          duration="35s"
          opacity={0.15}
          text={b3}
        />
        <BinaryColumn
          right="3%"
          delay="-18s"
          duration="24s"
          opacity={0.3}
          text={b1}
        />

        <div className="max-w-7xl mx-auto px-6 relative z-10">
          <div className="flex flex-col gap-12 lg:gap-16">
            {/* 1st from left */}
            <div className="flex flex-col md:flex-row items-center gap-8 lg:gap-12 w-full relative">
              <div className="w-full md:w-3/4 lg:w-2/3">
                <FeatureCard
                  icon={<Zap className="h-7 w-7 text-accent" />}
                  title="Live AI interviews"
                  desc={
                    <ul className="space-y-2 list-none p-0 m-0">
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Dynamic, follow-up enabled conversations.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Real-time adaptability to candidate responses.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Tailored specifically to the candidate's depth and tech
                        stack.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Consistent evaluation criteria across all similar roles.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Immediate feedback generation after the interview
                        concludes.
                      </li>
                    </ul>
                  }
                />
              </div>
              <div className="w-full md:w-1/4 lg:w-1/3 flex justify-center items-center opacity-50 pointer-events-none transition-opacity duration-500 hover:opacity-80">
                <img
                  src="/calrims/interview.png"
                  alt="Live AI Interview Dashboard"
                  className="w-full h-auto object-contain rounded-2xl drop-shadow-2xl border border-primary/10"
                />
              </div>
            </div>
            {/* 2nd from right */}
            <div className="flex flex-col md:flex-row-reverse items-center gap-8 lg:gap-12 w-full relative">
              <div className="w-full md:w-3/4 lg:w-2/3">
                <FeatureCard
                  className="tilt-up"
                  icon={<CheckCircle2 className="h-7 w-7 text-primary" />}
                  title="Signal-rich screening"
                  desc={
                    <ul className="space-y-2 list-none p-0 m-0">
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Advanced resume parsing with semantic understanding.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Calibrated scoring across multiple skill dimensions.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Objective evaluation of candidate reasoning.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Automated verification of core technical competencies.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Data-driven insights to highlight hidden talent.
                      </li>
                    </ul>
                  }
                />
              </div>
              <div className="w-full md:w-1/4 lg:w-1/3 flex justify-center items-center opacity-50 pointer-events-none transition-opacity duration-500 hover:opacity-80">
                <img
                  src="/calrims/portfolio.png"
                  alt="Signal-rich screening"
                  className="w-full h-auto object-contain rounded-2xl drop-shadow-2xl border border-primary/10"
                />
              </div>
            </div>
            {/* 3rd from left */}
            <div className="flex flex-col md:flex-row items-center gap-8 lg:gap-12 w-full relative">
              <div className="w-full md:w-3/4 lg:w-2/3">
                <FeatureCard
                  icon={<Users className="h-7 w-7 text-primary" />}
                  title="Unbiased decisions"
                  desc={
                    <ul className="space-y-2 list-none p-0 m-0">
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Standardized rubrics to eliminate personal bias.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Comprehensive reports that make every hire defensible.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Data-backed decision making for your entire team.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Transparent criteria visible to all stakeholders.
                      </li>
                      <li className="flex items-start gap-2">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary shrink-0" />{" "}
                        Consistent candidate experience from start to finish.
                      </li>
                    </ul>
                  }
                />
              </div>
              <div className="w-full md:w-1/4 lg:w-1/3 flex justify-center items-center opacity-50 pointer-events-none transition-opacity duration-500 hover:opacity-80">
                <img
                  src="/calrims/aim.png"
                  alt="Unbiased decisions"
                  className="w-full h-auto object-contain rounded-2xl drop-shadow-2xl border border-primary/10"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Dual Audience Section */}
      <section className="py-20 relative z-10">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-10 lg:gap-16 items-stretch">
            {/* Candidate Card */}
            <div className="group relative">
              <div
                className="absolute inset-0 rounded-3xl border border-white/50"
                style={{
                  background: "rgba(255,255,255,0.35)",
                  backdropFilter: "blur(18px)",
                  WebkitBackdropFilter: "blur(18px)",
                  boxShadow: "0 8px 32px rgba(59,130,246,0.10), inset 0 1px 0 rgba(255,255,255,0.5)",
                }}
              />
              <div className="relative rounded-3xl p-8 lg:p-10">
                <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-25 transition-opacity">
                  <Users className="h-32 w-32 text-primary" />
                </div>
                <h3 className="text-2xl lg:text-3xl font-semibold mb-6 text-slate-900 dark:text-white">
                  For candidates who are more than a resume
                </h3>
                <ul className="space-y-3 mb-8">
                  <ListItem text="Apply once, reuse your interview signal across roles." />
                  <ListItem text="Answer practical, scenario-based questions." />
                  <ListItem text="Get evaluated on technical accuracy, reasoning, and depth." />
                  <ListItem text="Stay in control with transparent, structured feedback." />
                </ul>
                <Link href="/jobs">
                  <Button
                    variant="link"
                    className="p-0 text-base text-primary hover:text-primary/80"
                  >
                    Browse openings &rarr;
                  </Button>
                </Link>
              </div>
            </div>

            {/* HR Card */}
            <div className="group relative">
              <div
                className="absolute inset-0 rounded-3xl border border-primary/30"
                style={{
                  background: "rgba(66, 99, 168, 0.40)",
                  backdropFilter: "blur(18px)",
                  WebkitBackdropFilter: "blur(18px)",
                  boxShadow: "0 30px 90px rgba(15,23,42,0.4), inset 0 1px 0 rgba(255,255,255,0.15)",
                }}
              />
              <div className="relative rounded-3xl p-8 lg:p-10 text-primary-foreground">
                <h3 className="text-2xl lg:text-3xl font-semibold mb-6">
                  For hiring teams shipping fast, not guessing
                </h3>
                <ul className="space-y-3 mb-8">
                  <ListItem
                    text="Spin up calibrated interview flows per role in minutes."
                    dark
                  />
                  <ListItem
                    text="See every candidate’s skill map in a single view."
                    dark
                  />
                  <ListItem text="Cut time-to-hire from weeks to days." dark />
                  <ListItem
                    text="Share crisp reports with founders, VPs, and panels."
                    dark
                  />
                </ul>
                <Link href="/auth/login?role=hr">
                  <Button
                    size="lg"
                    className="bg-slate-950 text-white hover:bg-slate-900 rounded-full px-7"
                  >
                    Open the HR dashboard
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <div className="relative z-10 w-full mt-20">
        <svg
          className="absolute top-0 w-full h-[60px] md:h-[100px] -mt-[59px] md:-mt-[99px] left-0 pointer-events-none"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 1440 320"
          preserveAspectRatio="none"
        >
          <path
            fill="#0a1a3c"
            fillOpacity="1"
            d="M0,96L48,112C96,128,192,160,288,160C384,160,480,128,576,112C672,96,768,96,864,112C960,128,1056,160,1152,165.3C1248,171,1344,149,1392,138.7L1440,128L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"
          ></path>
        </svg>
        <footer className="py-10 bg-[#0a1a3c] text-white">
          <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="flex items-center gap-2">
              <img
                src="/calrims/caldim-logo-dark.png"
                alt="Calrims Logo"
                className="h-9 w-auto"
              />
              <span className="text-md font-bold text-white/90">
                Caldim Engineering
              </span>
            </div>
            <p className="text-white/70 text-md md:text-md text-center max-w-xl">
              © {new Date().getFullYear()} Powered by Caldim Engineering. Built
              for teams who care about who they hire.
            </p>
            <div className="flex gap-5 text-md md:text-md">
              <a
                href="#"
                className="text-white/70 hover:text-white transition-colors"
              >
                Privacy
              </a>
              <a
                href="#"
                className="text-white/70 hover:text-white transition-colors"
              >
                Terms
              </a>
              <a
                href="#"
                className="text-white/70 hover:text-white transition-colors"
              >
                Updates
              </a>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}

const b1_base =
  "0\n1\n0\n1\n1\n0\n0\n1\n0\n1\n1\n1\n0\n0\n1\n0\n1\n0\n1\n0\n1\n1\n0\n0\n1\n0\n1\n1\n0\n1\n0\n1\n1\n0\n1\n0\n1\n1\n0\n0\n1\n0\n1\n0\n1\n0\n1\n0";
const b1 = `${b1_base}\n${b1_base}\n${b1_base}`;
const b2_base =
  "1\n0\n1\n0\n0\n1\n1\n0\n1\n0\n0\n1\n1\n0\n1\n0\n1\n0\n1\n0\n0\n1\n1\n0\n1\n0\n1\n0\n1\n0\n0\n1\n1\n0\n1\n0\n0\n1\n0\n1\n0\n1\n0\n1\n1\n0\n1\n0";
const b2 = `${b2_base}\n${b2_base}\n${b2_base}`;
const b3_base =
  "0\n0\n1\n1\n0\n1\n0\n0\n1\n1\n0\n1\n1\n0\n0\n1\n0\n1\n1\n0\n1\n0\n1\n0\n0\n1\n1\n0\n1\n1\n0\n0\n1\n1\n0\n1\n0\n1\n0\n0\n1\n1\n0\n1\n1\n0\n1\n0";
const b3 = `${b3_base}\n${b3_base}\n${b3_base}`;

function BinaryColumn({
  left,
  right,
  delay,
  duration,
  opacity,
  text,
}: {
  left?: string;
  right?: string;
  delay: string;
  duration: string;
  opacity: number;
  text: string;
}) {
  return (
    <div
      className="hidden md:flex flex-col absolute top-0 bottom-0 pointer-events-none select-none z-0"
      style={{
        left,
        right,
        opacity,
        overflow: "hidden",
        width: "18px",
        maskImage:
          "linear-gradient(to bottom, transparent, black 15%, black 85%, transparent)",
        WebkitMaskImage:
          "linear-gradient(to bottom, transparent, black 15%, black 85%, transparent)",
      }}
    >
      <div
        style={{
          fontSize: "15px",
          fontWeight: "bold",
          fontFamily: "monospace",
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
          lineHeight: "2.2",
          textAlign: "center",
          animation: `binaryFall ${duration} linear infinite ${delay}`,
        }}
      >
        <div className="text-primary/70">{text}</div>
        <div className="text-primary/70">{text}</div>
      </div>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  desc,
  className,
}: {
  icon: React.ReactNode;
  title: string;
  desc: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`glass-feature-card p-7 rounded-3xl group ${className || ""}`}
    >
      <div className="mb-5 inline-flex items-center justify-center rounded-2xl bg-white/80 shadow-sm px-3 py-2 group-hover:scale-105 transition-transform">
        {icon}
      </div>
      <h3 className="text-2xl font-bold tracking-tight mb-5 text-slate-900">{title}</h3>
      <div className="text-base font-medium text-slate-700 leading-relaxed space-y-1">
        {desc}
      </div>
    </div>
  );
}

function ListItem({ text, dark = false }: { text: string; dark?: boolean }) {
  return (
    <li
      className={`flex gap-3 items-center text-sm ${dark ? "text-white" : "text-slate-800"}`}
    >
      <div
        className={`p-1.5 rounded-full ${
          dark
            ? "bg-white/20 text-white"
            : "bg-primary/10 text-primary"
        }`}
      >
        <CheckCircle2 className="h-4 w-4" />
      </div>
      <span className="leading-relaxed">{text}</span>
    </li>
  );
}
