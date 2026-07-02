"use client";

import { useState, useRef, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { uploadResume, uploadResumeText, uploadJD, runAnalysis, getAnalysis, listResumes } from "@/lib/api";
import { Upload, FileText, Loader2, CheckCircle, XCircle, AlertTriangle, ChevronDown, ChevronUp, ClipboardPaste, User, RefreshCw } from "lucide-react";

type EvidenceItem = {
  skill: string;
  found_in_resume: boolean;
  similarity: number;
  evidence_snippets: string[];
  matched_by: string;
  match_reason?: string;
};

type AnalysisResult = {
  analysis_id?: string;
  status: string;
  score?: { overall_score: number; keyword_score: number; semantic_score: number; category_scores: Record<string, { score: number; matched: number; total: number }> };
  matched_skills?: { skill: string; matched_by: string; confidence?: number }[];
  missing_skills?: { skill: string; category: string; tip?: string }[];
  optimized_bullets?: { original: string; optimized: string; keywords_added: string[]; section?: string; section_label?: string }[];
  explainability?: { summary?: string; improvement_priority?: string[] };
  evidence?: EvidenceItem[];
  processing_time_ms?: number;
};

const STORAGE_KEY = "ats_last_result";

export default function AnalyzePage() {
  const { getToken } = useAuth();

  const [resumeSource, setResumeSource] = useState<"yours" | "new">("yours");
  const [storedResumeId, setStoredResumeId] = useState<string | null>(null);
  const [storedResumeName, setStoredResumeName] = useState<string | null>(null);
  const [loadingStored, setLoadingStored] = useState(false);

  const [resumeId, setResumeId] = useState<string | null>(null);
  const [resumeFile, setResumeFile] = useState<string | null>(null);
  const [resumeMode, setResumeMode] = useState<"file" | "text">("file");
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [step, setStep] = useState<"idle" | "uploading" | "analyzing" | "done" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [activeTab, setActiveTab] = useState<"gap" | "bullets">("gap");
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // Load persisted result on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        setResult(parsed);
        setStep("done");
      }
    } catch {}
  }, []);

  // Fetch stored resume
  useEffect(() => {
    if (resumeSource !== "yours") return;
    async function fetchStored() {
      setLoadingStored(true);
      try {
        const token = await getToken();
        if (!token) return;
        const data = await listResumes(token);
        const resumes: { resume_id: string; filename?: string; is_active?: boolean }[] = Array.isArray(data) ? data : [];
        const active = resumes.find((r) => r.is_active) ?? resumes[0];
        if (active) {
          setStoredResumeId(active.resume_id);
          setStoredResumeName(active.filename ?? "Your saved resume");
        } else {
          setStoredResumeId(null);
          setStoredResumeName(null);
        }
      } catch {
        setStoredResumeId(null);
      } finally {
        setLoadingStored(false);
      }
    }
    fetchStored();
  }, [resumeSource, getToken]);

  const activeResumeId = resumeSource === "yours" ? storedResumeId : resumeId;

  async function handleResumeUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setStep("uploading");
    try {
      const token = await getToken();
      const res = await uploadResume(token!, file);
      setResumeId(res.resume_id);
      setResumeFile(file.name);
      setStep("idle");
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Resume upload failed");
      setStep("error");
    }
  }

  async function handleResumeTextUpload() {
    if (!resumeText.trim()) return;
    setStep("uploading");
    try {
      const token = await getToken();
      const res = await uploadResumeText(token!, resumeText);
      setResumeId(res.resume_id);
      setResumeFile("Pasted text");
      setStep("idle");
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Resume upload failed");
      setStep("error");
    }
  }

  async function handleAnalyze() {
    if (!activeResumeId || !jdText.trim()) return;
    setStep("uploading");
    setResult(null);
    localStorage.removeItem(STORAGE_KEY);
    try {
      const token = await getToken();
      const jd = await uploadJD(token!, jdText);
      const analysis = await runAnalysis(token!, activeResumeId, jd.jd_id);
      setAnalysisId(analysis.analysis_id);
      setStep("analyzing");
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Analysis failed");
      setStep("error");
    }
  }

  function handleNewAnalysis() {
    setResult(null);
    setStep("idle");
    setJdText("");
    setAnalysisId(null);
    localStorage.removeItem(STORAGE_KEY);
  }

  // Poll for completion
  useEffect(() => {
    if (step !== "analyzing" || !analysisId) return;
    pollRef.current = setInterval(async () => {
      try {
        const token = await getToken();
        const data = await getAnalysis(token!, analysisId);
        if (data.status === "completed" || data.status === "failed") {
          clearInterval(pollRef.current!);
          if (data.status === "completed") {
            setResult(data);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
          }
          setStep(data.status === "completed" ? "done" : "error");
          if (data.status === "failed") setErrorMsg("Analysis failed on server.");
        }
      } catch {}
    }, 2500);
    return () => clearInterval(pollRef.current!);
  }, [step, analysisId, getToken]);

  const score = result?.score?.overall_score ?? 0;
  const scoreColor = score >= 70 ? "text-emerald-400" : score >= 50 ? "text-yellow-400" : "text-red-400";
  const scoreBg = score >= 70 ? "bg-emerald-500" : score >= 50 ? "bg-yellow-500" : "bg-red-500";
  const canAnalyze = !!activeResumeId && !!jdText.trim() && step !== "analyzing" && step !== "uploading";

  // Build evidence map for inline lookup
  const evidenceMap: Record<string, EvidenceItem> = {};
  result?.evidence?.forEach(e => { evidenceMap[e.skill.toLowerCase()] = e; });

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Analyze Resume</h1>
        {step === "done" && (
          <button onClick={handleNewAnalysis} className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-xl transition-colors">
            <RefreshCw className="w-4 h-4" /> New Analysis
          </button>
        )}
      </div>

      {/* Input panel - hide when results are shown */}
      {step !== "done" && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            {/* Resume panel */}
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-white font-semibold flex items-center gap-2">
                  <Upload className="w-4 h-4 text-indigo-400" /> Resume
                </h2>
                <div className="flex bg-gray-800 rounded-lg p-0.5 text-xs">
                  <button onClick={() => setResumeSource("yours")} className={`px-3 py-1 rounded-md transition-colors flex items-center gap-1 ${resumeSource === "yours" ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200"}`}>
                    <User className="w-3 h-3" /> Your Resume
                  </button>
                  <button onClick={() => setResumeSource("new")} className={`px-3 py-1 rounded-md transition-colors ${resumeSource === "new" ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200"}`}>
                    New Resume
                  </button>
                </div>
              </div>

              {resumeSource === "yours" && (
                loadingStored ? (
                  <div className="flex items-center gap-2 text-gray-400 text-sm py-4"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
                ) : storedResumeId ? (
                  <div className="flex items-center gap-2 bg-indigo-950/40 border border-indigo-800/40 rounded-xl px-4 py-3">
                    <CheckCircle className="w-5 h-5 text-indigo-400 shrink-0" />
                    <div><p className="text-indigo-300 text-sm font-medium">{storedResumeName}</p><p className="text-indigo-500 text-xs">Will be used for analysis</p></div>
                    <a href="/resume" className="ml-auto text-xs text-gray-500 hover:text-indigo-400 underline">manage</a>
                  </div>
                ) : (
                  <div className="bg-yellow-950/30 border border-yellow-800/40 rounded-xl px-4 py-3">
                    <p className="text-yellow-300 text-sm">No saved resume found.</p>
                    <a href="/resume" className="text-indigo-400 text-xs underline">Upload your resume →</a>
                  </div>
                )
              )}

              {resumeSource === "new" && (
                <div>
                  <div className="flex bg-gray-800 rounded-lg p-0.5 text-xs mb-4">
                    <button onClick={() => setResumeMode("file")} className={`px-3 py-1 rounded-md transition-colors ${resumeMode === "file" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-gray-200"}`}>Upload PDF</button>
                    <button onClick={() => setResumeMode("text")} className={`px-3 py-1 rounded-md transition-colors ${resumeMode === "text" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-gray-200"}`}>Paste Text</button>
                  </div>
                  {resumeFile && (
                    <div className="flex items-center gap-2 mb-3 bg-indigo-950/40 border border-indigo-800/40 rounded-xl px-3 py-2">
                      <CheckCircle className="w-4 h-4 text-indigo-400 shrink-0" />
                      <span className="text-indigo-300 text-sm">{resumeFile}</span>
                      <button onClick={() => { setResumeId(null); setResumeFile(null); setResumeText(""); }} className="ml-auto text-gray-600 hover:text-gray-400 text-xs">remove</button>
                    </div>
                  )}
                  {resumeMode === "file" ? (
                    <label className="block cursor-pointer">
                      <div className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${resumeFile ? "border-indigo-700" : "border-gray-700 hover:border-indigo-500"}`}>
                        <FileText className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                        <p className="text-gray-400 text-sm">{resumeFile ? "Click to replace PDF" : "Drop PDF here or click to upload"}</p>
                      </div>
                      <input type="file" accept=".pdf" className="hidden" onChange={handleResumeUpload} />
                    </label>
                  ) : (
                    <div>
                      <textarea className="w-full h-36 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-200 placeholder-gray-500 resize-none focus:outline-none focus:border-indigo-500" placeholder="Paste your resume text here..." value={resumeText} onChange={(e) => setResumeText(e.target.value)} />
                      <button onClick={handleResumeTextUpload} disabled={!resumeText.trim() || step === "uploading"} className="mt-2 w-full py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-gray-200 text-sm rounded-xl flex items-center justify-center gap-2 transition-colors">
                        {step === "uploading" ? <Loader2 className="w-4 h-4 animate-spin" /> : <ClipboardPaste className="w-4 h-4" />}
                        {step === "uploading" ? "Uploading…" : "Use This Resume"}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* JD */}
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
              <h2 className="text-white font-semibold mb-4 flex items-center gap-2"><FileText className="w-4 h-4 text-indigo-400" /> Job Description</h2>
              <textarea className="w-full h-48 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-200 placeholder-gray-500 resize-none focus:outline-none focus:border-indigo-500" placeholder="Paste the job description here…" value={jdText} onChange={(e) => setJdText(e.target.value)} />
            </div>
          </div>

          <div className="flex justify-center mb-8">
            <button onClick={handleAnalyze} disabled={!canAnalyze} className="px-10 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors flex items-center gap-2">
              {(step === "analyzing" || step === "uploading") && <Loader2 className="w-4 h-4 animate-spin" />}
              {step === "analyzing" ? "Analyzing…" : step === "uploading" ? "Uploading…" : "Analyze"}
            </button>
          </div>
        </>
      )}

      {step === "error" && (
        <div className="bg-red-950 border border-red-800 rounded-xl p-4 mb-6 flex items-center gap-3">
          <XCircle className="w-5 h-5 text-red-400 shrink-0" />
          <p className="text-red-300 text-sm">{errorMsg}</p>
        </div>
      )}

      {step === "analyzing" && <AnalysisProgress />}

      {/* Results */}
      {step === "done" && result && (
        <div className="space-y-6">
          {/* Score banner */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 flex items-center gap-8">
            <div className="text-center">
              <p className={`text-5xl font-bold ${scoreColor}`}>{score.toFixed(1)}%</p>
              <p className="text-gray-500 text-xs mt-1">ATS Score</p>
            </div>
            <div className="flex-1 space-y-2">
              {[{ label: "Keyword", val: result.score?.keyword_score ?? 0 }, { label: "Semantic", val: result.score?.semantic_score ?? 0 }].map(({ label, val }) => (
                <div key={label}>
                  <div className="flex justify-between text-xs text-gray-400 mb-1"><span>{label}</span><span>{val.toFixed(1)}%</span></div>
                  <div className="h-2 bg-gray-800 rounded-full overflow-hidden"><div className={`h-full ${scoreBg} opacity-70 rounded-full`} style={{ width: `${val}%` }} /></div>
                </div>
              ))}
            </div>
            {result.processing_time_ms && <p className="text-xs text-gray-600">⏱ {(result.processing_time_ms / 1000).toFixed(1)}s</p>}
          </div>

          {result.explainability?.summary && (
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
              <p className="text-gray-300 text-sm leading-relaxed">{result.explainability.summary}</p>
            </div>
          )}

          {/* Tabs */}
          <div className="flex gap-2 border-b border-gray-800">
            {(["gap", "bullets"] as const).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)} className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${activeTab === tab ? "border-indigo-500 text-indigo-400" : "border-transparent text-gray-500 hover:text-gray-300"}`}>
                {tab === "gap" ? "Skills Gap & Evidence" : "Optimized Bullets"}
              </button>
            ))}
          </div>

          {/* Skills Gap + Evidence combined */}
          {activeTab === "gap" && (
            <div className="space-y-6">
              {/* Matched skills with inline evidence */}
              <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
                <h3 className="text-white font-semibold mb-4">Matched Skills</h3>
                <div className="space-y-3">
                  {result.matched_skills?.map((s) => {
                    const ev = evidenceMap[s.skill.toLowerCase()];
                    return (
                      <div key={s.skill} className="border border-gray-800 rounded-xl p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
                          <span className="text-gray-200 text-sm font-medium">{s.skill}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full ml-auto ${s.matched_by === "exact" || s.matched_by === "normalized" ? "bg-emerald-900/50 text-emerald-400" : "bg-indigo-900/50 text-indigo-400"}`}>
                            {s.matched_by === "exact" || s.matched_by === "normalized" ? "exact" : s.matched_by}
                          </span>
                        </div>
                        {ev?.evidence_snippets?.[0] && (
                          <p className="text-xs text-gray-400 font-mono bg-gray-800 rounded-lg px-4 py-3 leading-relaxed whitespace-pre-wrap break-words">"{ev.evidence_snippets[0].trim()}"</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Missing skills */}
              {result.missing_skills && result.missing_skills.length > 0 && (
                <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
                  <h3 className="text-white font-semibold mb-4">Missing Skills</h3>
                  <div className="space-y-3">
                    {result.missing_skills.map((s) => (
                      <div key={s.skill}>
                        <div className="flex items-center gap-2 text-sm">
                          <XCircle className="w-4 h-4 text-red-400 shrink-0" />
                          <span className="text-gray-200">{s.skill}</span>
                          <span className="text-gray-600 text-xs ml-auto">{s.category}</span>
                        </div>
                        {s.tip && (
                          <div className="ml-6 mt-1 bg-yellow-950/40 border border-yellow-800/40 rounded-lg px-3 py-2">
                            <p className="text-yellow-300 text-xs flex items-start gap-1"><AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />{s.tip}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Optimized Bullets */}
          {activeTab === "bullets" && (
            <div className="space-y-4">
              {result.optimized_bullets?.length ? (
                result.optimized_bullets.map((b, i) => <BulletCard key={i} index={i + 1} bullet={b} />)
              ) : (
                <p className="text-gray-500 text-sm">No bullets generated.</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AnalysisProgress() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => setElapsed(Date.now() - start), 200);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="max-w-md mx-auto py-24 flex flex-col items-center gap-4">
      <Loader2 className="w-10 h-10 text-indigo-400 animate-spin" />
      <p className="text-white font-medium">Analyzing your resume against the job description...</p>
      <p className="text-gray-500 text-xs">{(elapsed / 1000).toFixed(0)}s elapsed</p>
    </div>
  );
}

function BulletCard({ index, bullet }: { index: number; bullet: { original: string; optimized: string; keywords_added: string[]; section_label?: string } }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
      <button onClick={() => setOpen(!open)} className="w-full flex justify-between items-start gap-3 text-left">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <p className="text-gray-500 text-xs">Bullet {index}</p>
            {bullet.section_label && <span className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded-full border border-gray-700">{bullet.section_label}</span>}
          </div>
          <p className="text-gray-300 text-sm line-clamp-2">{bullet.original}</p>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-gray-500 shrink-0 mt-1" /> : <ChevronDown className="w-4 h-4 text-gray-500 shrink-0 mt-1" />}
      </button>
      {open && (
        <div className="mt-4 space-y-3">
          <div><p className="text-xs text-gray-500 mb-1">Original</p><p className="text-gray-400 text-sm bg-gray-800 rounded-lg px-3 py-2">{bullet.original}</p></div>
          <div><p className="text-xs text-emerald-400 mb-1">✨ Optimized</p><p className="text-gray-200 text-sm bg-emerald-950/30 border border-emerald-800/40 rounded-lg px-3 py-2">{bullet.optimized}</p></div>
          {bullet.keywords_added?.length > 0 && (
            <div className="flex flex-wrap gap-1">{bullet.keywords_added.map((k) => <span key={k} className="text-xs bg-indigo-900/50 text-indigo-300 px-2 py-0.5 rounded-full">{k}</span>)}</div>
          )}
        </div>
      )}
    </div>
  );
}
