"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserButton } from "@clerk/nextjs";
import { LayoutDashboard, Search, Brain, History, FileText, MessageSquare } from "lucide-react";

const NAV = [
  { href: "/", label: "Home", icon: LayoutDashboard },
  { href: "/resume", label: "My Resume", icon: FileText },
  { href: "/analyze", label: "Analyze", icon: Search },
  { href: "/skills", label: "My Skill Validation", icon: Brain },
  { href: "/dashboard", label: "Dashboard", icon: History },
  { href: "/feedback", label: "Feedback", icon: MessageSquare },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="fixed left-0 top-0 h-full w-56 bg-gray-900 border-r border-gray-800 flex flex-col z-10">
      <div className="px-5 py-5 border-b border-gray-800">
        <span className="text-lg font-bold text-indigo-400">AI Job Copilot</span>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = path === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:bg-gray-800 hover:text-gray-100"
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="px-5 py-4 border-t border-gray-800 flex items-center gap-3">
        <UserButton />
        <span className="text-xs text-gray-500">Account</span>
      </div>
    </aside>
  );
}
