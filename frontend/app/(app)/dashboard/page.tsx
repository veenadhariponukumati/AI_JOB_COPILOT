"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { getHistory } from "@/lib/api";
import { History, Loader2, TrendingUp, Copy, Check } from "lucide-react";

type HistoryItem = {
  analysis_id: string;
  status: string;
  overall_score: number | null;
  jd_title: string | null;
  resume_filename: string | null;
  created_at: string;
};

export default function DashboardPage() {
  const { getToken } = useAuth();
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      try {
        const data = await getHistory(token!);
        setHistory(data);
      } catch {}
      setLoading(false);
    })();
  }, [getToken]);

  function copyId(id: string) {
    navigator.clipboard.writeText(id);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  }

  const scores = history.filter((h) => h.overall_score != null).map((h) => h.overall_score!);
  const avgScore = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  const best = scores.length ? Math.max(...scores) : null;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <History className="w-6 h-6 text-indigo-400" />
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
      </div>

      {/* Stats */}
      {history.length > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: "Total Analyses", value: history.length },
            { label: "Avg Score", value: avgScore != null ? `${avgScore.toFixed(1)}%` : "N/A" },
            { label: "Best Score", value: best != null ? `${best.toFixed(1)}%` : "N/A" },
          ].map(({ label, value }) => (
            <div key={label} className="bg-gray-900 border border-gray-800 rounded-2xl p-5 text-center">
              <p className="text-2xl font-bold text-indigo-400">{value}</p>
              <p className="text-gray-500 text-xs mt-1">{label}</p>
            </div>
          ))}
        </div>
      )}

      {history.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-10 text-center">
          <TrendingUp className="w-12 h-12 text-gray-700 mx-auto mb-4" />
          <p className="text-gray-400">No analyses yet. Go to Analyze to run your first one.</p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-gray-500 mb-2">Copy an Analysis ID to use it in My Skills quizzes.</p>
          {history.map((item) => {
            const score = item.overall_score;
            const scoreColor = score == null ? "text-gray-500" : score >= 70 ? "text-emerald-400" : score >= 50 ? "text-yellow-400" : "text-red-400";
            const date = new Date(item.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

            return (
              <div key={item.analysis_id} className="bg-gray-900 border border-gray-800 rounded-2xl p-5 flex items-center gap-5">
                <div className="text-center w-16 shrink-0">
                  <p className={`text-xl font-bold ${scoreColor}`}>
                    {score != null ? `${score.toFixed(0)}%` : "N/A"}
                  </p>
                  <p className="text-gray-600 text-xs">score</p>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">{item.jd_title ?? "Untitled Job"}</p>
                  <p className="text-gray-500 text-xs truncate">{item.resume_filename ?? "Unnamed resume"} · {date}</p>
                  <p className="text-gray-700 text-xs font-mono mt-1 truncate">{item.analysis_id}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${item.status === "completed" ? "bg-emerald-900/50 text-emerald-400" : item.status === "failed" ? "bg-red-900/50 text-red-400" : "bg-gray-800 text-gray-500"}`}>
                    {item.status}
                  </span>
                  <button
                    onClick={() => copyId(item.analysis_id)}
                    className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-colors"
                    title="Copy analysis ID"
                  >
                    {copied === item.analysis_id ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
