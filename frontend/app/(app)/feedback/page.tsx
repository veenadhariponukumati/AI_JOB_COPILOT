"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { submitFeedback, getMyFeedback } from "@/lib/api";
import { MessageSquare, Loader2, CheckCircle, AlertTriangle } from "lucide-react";

type FeedbackEntry = {
  feedback_id: string;
  category: string;
  message: string;
  created_at: string;
};

const CATEGORIES = [
  { value: "suggestion", label: "Suggestion" },
  { value: "bug", label: "Bug report" },
  { value: "general", label: "General feedback" },
];

const CATEGORY_STYLES: Record<string, string> = {
  suggestion: "bg-indigo-950/50 text-indigo-300 border-indigo-800/40",
  bug: "bg-red-950/50 text-red-300 border-red-800/40",
  general: "bg-gray-800 text-gray-300 border-gray-700",
};

export default function FeedbackPage() {
  const { getToken } = useAuth();
  const [category, setCategory] = useState("suggestion");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");
  const [entries, setEntries] = useState<FeedbackEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const token = await getToken();
      if (!token) { setLoading(false); return; }
      const data = await getMyFeedback(token);
      setEntries(Array.isArray(data) ? data : []);
    } catch {}
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  async function handleSubmit() {
    if (!message.trim()) return;
    setSubmitting(true);
    setError("");
    setSuccess("");
    try {
      const token = await getToken();
      await submitFeedback(token!, category, message.trim());
      setMessage("");
      setSuccess("Thanks, your feedback has been recorded.");
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to submit feedback.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <MessageSquare className="w-6 h-6 text-indigo-400" />
        <h1 className="text-2xl font-bold text-white">Feedback & Suggestions</h1>
      </div>
      <p className="text-gray-400 text-sm mb-8">
        Found a bug, have an idea, or just want to share your thoughts? Let me know below.
      </p>

      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-8">
        <div className="flex bg-gray-800 rounded-lg p-0.5 text-xs mb-4 w-fit">
          {CATEGORIES.map((c) => (
            <button
              key={c.value}
              onClick={() => setCategory(c.value)}
              className={`px-3 py-1.5 rounded-md transition-colors ${category === c.value ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200"}`}
            >
              {c.label}
            </button>
          ))}
        </div>

        <textarea
          className="w-full h-36 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-200 placeholder-gray-500 resize-none focus:outline-none focus:border-indigo-500"
          placeholder="Tell me what's on your mind..."
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />

        <button
          onClick={handleSubmit}
          disabled={!message.trim() || submitting}
          className="mt-3 w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium rounded-xl flex items-center justify-center gap-2 transition-colors"
        >
          {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
          {submitting ? "Submitting..." : "Submit feedback"}
        </button>

        {error && (
          <div className="mt-4 flex items-center gap-2 bg-red-950/50 border border-red-800/50 rounded-xl px-4 py-2">
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
            <p className="text-red-300 text-sm">{error}</p>
          </div>
        )}
        {success && (
          <div className="mt-4 flex items-center gap-2 bg-emerald-950/50 border border-emerald-800/50 rounded-xl px-4 py-2">
            <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
            <p className="text-emerald-300 text-sm">{success}</p>
          </div>
        )}
      </div>

      <div>
        <h2 className="text-white font-semibold mb-4">Your Past Feedback</h2>
        {loading ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading...
          </div>
        ) : entries.length === 0 ? (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 text-center">
            <MessageSquare className="w-8 h-8 text-gray-700 mx-auto mb-3" />
            <p className="text-gray-500 text-sm">You haven't submitted any feedback yet.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {entries.map((e) => (
              <div key={e.feedback_id} className="bg-gray-900 border border-gray-800 rounded-2xl px-5 py-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${CATEGORY_STYLES[e.category] ?? CATEGORY_STYLES.general}`}>
                    {CATEGORIES.find((c) => c.value === e.category)?.label ?? e.category}
                  </span>
                  <span className="text-gray-600 text-xs ml-auto">{new Date(e.created_at).toLocaleDateString()}</span>
                </div>
                <p className="text-gray-300 text-sm leading-relaxed">{e.message}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
