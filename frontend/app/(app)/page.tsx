"use client";

import Link from "next/link";
import { useUser } from "@clerk/nextjs";
import { Search, Brain, History, Upload } from "lucide-react";

const CARDS = [
  {
    href: "/analyze",
    icon: Search,
    title: "Analyze Resume",
    desc: "Upload your resume, paste a job description, and get an instant ATS score with skills gap analysis.",
    cta: "Start Analysis",
    color: "from-indigo-500 to-indigo-700",
  },
  {
    href: "/skills",
    icon: Brain,
    title: "My Skill Validation",
    desc: "Take quizzes on missing skills. Track your progress from easy to medium to hard. Know when you're ready to apply.",
    cta: "Validate Skills",
    color: "from-violet-500 to-violet-700",
  },
  {
    href: "/dashboard",
    icon: History,
    title: "Dashboard",
    desc: "See your full analysis history, score trends, and how your resume has improved over time.",
    cta: "View History",
    color: "from-emerald-500 to-emerald-700",
  },
];

export default function HomePage() {
  const { user } = useUser();
  const first = user?.firstName ?? "";

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-10 md:mb-14 text-center">
        <div className="mx-auto" style={{ maxWidth: "800px" }}>
          <h1
            className="text-white font-normal leading-tight text-[28px] sm:text-[40px] md:text-[48px]"
            style={{ fontFamily: "Georgia, serif" }}
          >
            <span className="typewriter-heading">Welcome to AI Job Copilot</span>
          </h1>
          <div
            className="fade-up mx-auto mt-1 h-[2px] bg-indigo-400 w-1/2 sm:w-3/5"
            style={{ maxWidth: "520px", animationDelay: "1.2s" }}
          />
          <div className="flex items-baseline justify-center flex-wrap gap-x-1 mt-4 sm:mt-5">
            {first && (
              <p
                className="fade-up text-gray-300 font-normal text-lg sm:text-xl"
                style={{ fontFamily: "Georgia, serif", animationDelay: "1.4s" }}
              >
                {first},
              </p>
            )}
            <p
              className="fade-up text-gray-400 font-normal text-lg sm:text-xl"
              style={{ fontFamily: "Georgia, serif", animationDelay: "1.7s" }}
            >
              I&apos;m glad you found some time to try out my site.
            </p>
          </div>
        </div>
        <div className="mt-10 sm:mt-14 space-y-4 text-gray-300 text-base leading-relaxed text-left">
          <p className="fade-up" style={{ animationDelay: "1.9s" }}>
            No resume is perfect. And that&apos;s okay.
          </p>
          <p className="fade-up" style={{ animationDelay: "2.1s" }}>
            Candidates get hired every day without being a perfect match for every job posting.
          </p>
          <p className="fade-up" style={{ animationDelay: "2.3s" }}>
            Rather than spending hours rewriting your resume for hundreds of applications, I believe in applying with the experience you&apos;ve actually built. The experience you know, understand, and can confidently talk about.
          </p>
          <p className="fade-up" style={{ animationDelay: "2.5s" }}>
            Confidence comes from knowing your own work, not from endlessly rewriting bullet points.
          </p>
          <p className="fade-up" style={{ animationDelay: "2.7s" }}>
            Before you begin, here&apos;s a quick introduction to AI Job Copilot below:
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10 fade-up" style={{ animationDelay: "2.95s" }}>
        {CARDS.map(({ href, icon: Icon, title, desc, cta, color }) => (
          <Link
            key={href}
            href={href}
            className="group bg-gray-900 border border-gray-800 rounded-2xl p-6 hover:border-indigo-500 transition-all"
          >
            <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${color} flex items-center justify-center mb-4`}>
              <Icon className="w-5 h-5 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-2">{title}</h3>
            <p className="text-gray-400 text-sm mb-4 leading-relaxed">{desc}</p>
            <span className="text-indigo-400 text-sm font-medium group-hover:underline">{cta} →</span>
          </Link>
        ))}
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 fade-up" style={{ animationDelay: "3.15s" }}>
        <div className="flex items-center gap-3 mb-4">
          <Upload className="w-5 h-5 text-indigo-400" />
          <h2 className="text-white font-semibold">Quick Start</h2>
        </div>
        <ol className="space-y-2 text-sm text-gray-400">
          <li><span className="text-indigo-400 font-medium">1.</span> Go to <Link href="/analyze" className="text-indigo-400 hover:underline">Analyze</Link> and upload your resume (PDF)</li>
          <li><span className="text-indigo-400 font-medium">2.</span> Paste the job description you're targeting</li>
          <li><span className="text-indigo-400 font-medium">3.</span> Click Analyze to get your ATS score, skills gap, and optimized bullets</li>
          <li><span className="text-indigo-400 font-medium">4.</span> Go to <Link href="/skills" className="text-indigo-400 hover:underline">My Skill Validation</Link> to quiz yourself on missing skills</li>
        </ol>
      </div>
    </div>
  );
}
