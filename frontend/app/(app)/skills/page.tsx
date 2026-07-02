"use client";

import { useState, useEffect, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { getSkillProgress, getResumeSkills, startQuiz, submitQuiz, clearSkillProgress, removeSkillProgress } from "@/lib/api";
import { Brain, CheckCircle, XCircle, Trophy, Loader2, ChevronRight, FileText, AlertTriangle, X, Trash2 } from "lucide-react";

type SkillProgress = {
  skill_name: string;
  highest_level_passed: string;
  ready_to_apply: string;
  is_resolved: boolean;
  easy_passed_at: string | null;
  medium_passed_at: string | null;
  hard_passed_at: string | null;
};

type ResumeSkill = { skill: string; category: string };

type QuizState = {
  quiz_id: string;
  skill: string;
  difficulty: string;
  questions: { question_id: number; question: string; options: string[] }[];
};

type QuizResult = {
  score: number;
  passed: string;
  correct_answers: number;
  total_questions: number;
};

const LEVELS = ["easy", "medium", "hard"] as const;
const LEVEL_LABELS = { easy: "Easy", medium: "Medium", hard: "Hard" };

const STORAGE_KEY = "ats_last_result";

function nextLevel(highest: string): string {
  if (highest === "none" || highest === "") return "easy";
  if (highest === "easy") return "medium";
  if (highest === "medium") return "hard";
  return "done";
}

export default function SkillsPage() {
  const { getToken } = useAuth();
  const [resumeSkills, setResumeSkills] = useState<ResumeSkill[]>([]);
  const [resumeFilename, setResumeFilename] = useState<string | null>(null);
  const [resumeSkillsError, setResumeSkillsError] = useState<string | null>(null);
  const [resumeSkillsLoading, setResumeSkillsLoading] = useState(false);
  const [resumeSkillsPending, setResumeSkillsPending] = useState(false);
  const [gapSkills, setGapSkills] = useState<SkillProgress[]>([]);
  const [loading, setLoading] = useState(true);
  const [quiz, setQuiz] = useState<QuizState | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [quizResult, setQuizResult] = useState<QuizResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [startingQuiz, setStartingQuiz] = useState(false);
  const quizRequestId = useRef(0);
  const isStartingRef = useRef(false);

  // Get analysisId from localStorage (set by analyze page)
  const [analysisId, setAnalysisId] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.analysis_id) setAnalysisId(parsed.analysis_id);
      }
    } catch {}
  }, []);

  async function fetchResumeSkills(token: string, isPoll = false) {
    if (!isPoll) setResumeSkillsLoading(true);
    setResumeSkillsError(null);
    try {
      const resumeData = await getResumeSkills(token);
      setResumeSkills(resumeData.skills ?? []);
      setResumeFilename(resumeData.resume_filename ?? null);
      if (resumeData.pending) {
        setResumeSkillsPending(true);
        setResumeSkillsLoading(false);
        setTimeout(async () => {
          const freshToken = await getToken();
          if (freshToken) fetchResumeSkills(freshToken, true);
        }, 5000);
        return;
      }
      setResumeSkillsPending(false);
      if (resumeData.error) setResumeSkillsError(resumeData.error);
    } catch (err: unknown) {
      setResumeSkillsPending(false);
      setResumeSkillsError(err instanceof Error ? err.message : "Failed to extract skills");
    }
    setResumeSkillsLoading(false);
  }

  useEffect(() => {
    (async () => {
      const token = await getToken();
      if (!token) { setLoading(false); return; }
      try {
        const progressData = await getSkillProgress(token);
        setGapSkills(progressData ?? []);
      } catch {}
      setLoading(false);
      fetchResumeSkills(token);
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getToken]);

  async function handleStartQuiz(skill: string, difficulty: string) {
    if (!analysisId) {
      alert("Run an analysis first. Analysis ID is needed to start a quiz.");
      return;
    }
    if (isStartingRef.current) return;
    isStartingRef.current = true;
    const requestId = ++quizRequestId.current;
    setStartingQuiz(true);
    // Clear any previous quiz/result immediately so a slow network request
    // never leaves stale quiz data on screen for the user to interact with.
    setQuiz(null);
    setQuizResult(null);
    setAnswers({});
    const token = await getToken();
    try {
      const q = await startQuiz(token!, analysisId, skill, difficulty);
      if (requestId !== quizRequestId.current) return;
      setQuiz({ ...q, difficulty });
      setAnswers({});
      setQuizResult(null);
    } catch (err: unknown) {
      if (requestId !== quizRequestId.current) return;
      alert(err instanceof Error ? err.message : "Failed to start quiz");
    } finally {
      isStartingRef.current = false;
      if (requestId === quizRequestId.current) setStartingQuiz(false);
    }
  }

  async function handleSubmitQuiz() {
    if (!quiz) return;
    setSubmitting(true);
    const token = await getToken();
    try {
      const result = await submitQuiz(token!, quiz.quiz_id, answers);
      setQuizResult(result);
      const updated = await getSkillProgress(token!);
      setGapSkills(updated);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Submit failed");
    }
    setSubmitting(false);
  }

  async function handleClearAll() {
    if (!confirm("Clear all tracked skills and quiz progress? This cannot be undone.")) return;
    const token = await getToken();
    try {
      await clearSkillProgress(token!);
      setGapSkills([]);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to clear skills");
    }
  }

  async function handleDismiss(skillName: string) {
    const token = await getToken();
    try {
      await removeSkillProgress(token!, skillName);
      setGapSkills((prev) => prev.filter((s) => s.skill_name !== skillName));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to remove skill");
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 animate-spin text-indigo-400" /></div>;
  }

  if (startingQuiz && !quiz) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
        <p className="text-gray-400 text-sm">Generating your quiz...</p>
      </div>
    );
  }

  // Quiz view
  if (quiz && !quizResult) {
    const answered = Object.keys(answers).length;
    const total = quiz.questions.length;
    return (
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <Brain className="w-5 h-5 text-indigo-400" />
          <h1 className="text-xl font-bold text-white">{quiz.skill} -{LEVEL_LABELS[quiz.difficulty as keyof typeof LEVEL_LABELS]} Quiz</h1>
          <span className="ml-auto text-sm text-gray-500">{answered}/{total} answered</span>
        </div>
        <div className="space-y-6">
          {quiz.questions.map((q) => (
            <div key={q.question_id} className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
              <p className="text-gray-200 text-sm font-medium mb-4">{q.question}</p>
              <div className="space-y-2">
                {q.options.map((opt) => (
                  <button key={opt} onClick={() => setAnswers((a) => ({ ...a, [q.question_id]: opt }))}
                    className={`w-full text-left px-4 py-2.5 rounded-xl text-sm transition-colors border ${answers[q.question_id] === opt ? "border-indigo-500 bg-indigo-950/50 text-indigo-200" : "border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-200"}`}>
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
        {answered < total && (
          <p className="mt-4 text-yellow-400 text-sm text-center">Please answer all questions to enable submit.</p>
        )}
        <div className="mt-4 flex gap-3">
          <button onClick={() => setQuiz(null)} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200">Cancel</button>
          <button onClick={handleSubmitQuiz} disabled={answered < total || submitting}
            className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-semibold rounded-xl text-sm flex items-center justify-center gap-2">
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />} Submit Quiz
          </button>
        </div>
      </div>
    );
  }

  // Quiz result view
  if (quizResult && quiz) {
    const passed = quizResult.passed === "pass";
    const next = nextLevel(quiz.difficulty);
    return (
      <div className="max-w-lg mx-auto text-center">
        <div className={`w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6 ${passed ? "bg-emerald-900" : "bg-red-900"}`}>
          {passed ? <Trophy className="w-10 h-10 text-emerald-400" /> : <XCircle className="w-10 h-10 text-red-400" />}
        </div>
        <h2 className="text-2xl font-bold text-white mb-2">{passed ? "Passed!" : "Not quite"}</h2>
        <p className="text-gray-400 mb-4">{quizResult.correct_answers}/{quizResult.total_questions} correct -{quizResult.score.toFixed(0)}%</p>
        {passed && next !== "done" && (
          <p className="text-indigo-300 text-sm mb-2">Next: take the <strong>{LEVEL_LABELS[next as keyof typeof LEVEL_LABELS]}</strong> quiz to level up.</p>
        )}
        {passed && next === "done" && (
          <div className="bg-emerald-950/30 border border-emerald-700 rounded-xl p-4 mb-6 text-emerald-300 text-sm">
            All levels complete! You are ready to apply this skill in a project and add it to your resume.
          </div>
        )}
        <div className="flex gap-3 justify-center mt-4">
          <button onClick={() => { setQuiz(null); setQuizResult(null); }} className="px-6 py-2 bg-gray-800 hover:bg-gray-700 text-gray-200 rounded-xl text-sm">Back to Skills</button>
          {passed && next !== "done" && (
            <button onClick={() => handleStartQuiz(quiz.skill, next)} className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-medium">
              Take {LEVEL_LABELS[next as keyof typeof LEVEL_LABELS]} Quiz <ChevronRight className="inline w-3 h-3" />
            </button>
          )}
        </div>
      </div>
    );
  }

  const activeGapSkills = gapSkills.filter((s) => !s.is_resolved);
  const resolvedGapSkills = gapSkills.filter((s) => s.is_resolved);

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div className="flex items-center gap-3">
        <Brain className="w-6 h-6 text-indigo-400" />
        <h1 className="text-2xl font-bold text-white">My Skill Validation</h1>
      </div>

      {/* Section 1: Resume Skills */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-4">
          <FileText className="w-4 h-4 text-indigo-400" />
          <h2 className="text-white font-semibold">Your Resume Skills</h2>
          {resumeFilename && <span className="text-xs text-gray-500 ml-auto">{resumeFilename}</span>}
        </div>
        {resumeSkillsLoading ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm py-4">
            <Loader2 className="w-4 h-4 animate-spin" /> Extracting skills from your resume…
          </div>
        ) : resumeSkillsPending ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm py-4">
            <Loader2 className="w-4 h-4 animate-spin" /> Still extracting skills from your recently uploaded resume, this can take up to a minute…
          </div>
        ) : resumeSkillsError ? (
          <div className="bg-red-950/30 border border-red-800/40 rounded-xl px-4 py-3">
            <p className="text-red-400 text-sm mb-2">Could not extract skills: {resumeSkillsError}</p>
            <button onClick={async () => { const t = await getToken(); if (t) fetchResumeSkills(t); }}
              className="text-xs text-indigo-400 underline">Retry</button>
          </div>
        ) : resumeSkills.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-500 text-sm">No resume uploaded yet.</p>
            <a href="/resume" className="text-indigo-400 text-sm underline mt-2 inline-block">Upload your resume →</a>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {resumeSkills.map((s) => (
              <span key={s.skill} className="px-3 py-1 bg-gray-800 border border-gray-700 text-gray-300 text-sm rounded-full">
                {s.skill}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Section 2: Skills to Validate (gap skills from analyses) */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-1">
          <AlertTriangle className="w-4 h-4 text-yellow-400" />
          <h2 className="text-white font-semibold">Skills to Validate</h2>
          {gapSkills.length > 0 && (
            <button onClick={handleClearAll} className="ml-auto text-xs text-gray-500 hover:text-red-400 flex items-center gap-1">
              <Trash2 className="w-3 h-3" /> Clear all
            </button>
          )}
        </div>
        <p className="text-gray-500 text-xs mb-4">Gap skills found in your analyses. Take quizzes to validate them, easy to medium to hard.</p>

        {!analysisId && activeGapSkills.length > 0 && (
          <div className="bg-yellow-950/30 border border-yellow-800/40 rounded-xl px-4 py-2 mb-4 text-yellow-300 text-xs flex items-center gap-2">
            <AlertTriangle className="w-3 h-3 shrink-0" /> Run an analysis first to unlock quizzes. Analysis ID is auto-detected from your last run.
          </div>
        )}

        {gapSkills.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-500 text-sm">No gap skills tracked yet. Run an analysis to discover missing skills.</p>
            <a href="/analyze" className="text-indigo-400 text-sm underline mt-2 inline-block">Analyze a job →</a>
          </div>
        ) : (
          <div className="space-y-3">
            {activeGapSkills.map((s) => {
              const next = nextLevel(s.highest_level_passed);
              const done = next === "done";
              return (
                <div key={s.skill_name} className="border border-gray-800 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-white text-sm font-medium">{s.skill_name}</span>
                      {done && <span className="text-xs bg-emerald-900 text-emerald-300 px-2 py-0.5 rounded-full flex items-center gap-1"><Trophy className="w-3 h-3" /> Ready to apply</span>}
                    </div>
                    {!done && (
                      <button onClick={() => handleStartQuiz(s.skill_name, next)}
                        className="text-xs bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 text-white px-3 py-1.5 rounded-lg flex items-center gap-1"
                        disabled={!analysisId || startingQuiz}>
                        {startingQuiz ? <Loader2 className="w-3 h-3 animate-spin" /> : <>{LEVEL_LABELS[next as keyof typeof LEVEL_LABELS]} Quiz <ChevronRight className="w-3 h-3" /></>}
                      </button>
                    )}
                  </div>
                  <div className="flex gap-2">
                    {LEVELS.map((lvl) => {
                      const p = (lvl === "easy" && s.easy_passed_at) || (lvl === "medium" && s.medium_passed_at) || (lvl === "hard" && s.hard_passed_at);
                      return (
                        <button
                          key={lvl}
                          onClick={() => handleStartQuiz(s.skill_name, lvl)}
                          disabled={!analysisId || startingQuiz}
                          title={p ? `Retake ${LEVEL_LABELS[lvl]} quiz` : `Take ${LEVEL_LABELS[lvl]} quiz`}
                          className={`flex-1 rounded-lg py-1.5 text-center text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${p ? "bg-emerald-900/50 text-emerald-300 border border-emerald-700 hover:bg-emerald-900/70" : "bg-gray-800 text-gray-500 border border-gray-700 hover:border-indigo-600 hover:text-gray-200"}`}
                        >
                          {p && <CheckCircle className="w-3 h-3 inline mr-1" />}{LEVEL_LABELS[lvl]}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}

            {resolvedGapSkills.length > 0 && (
              <div className="pt-2">
                <p className="text-xs text-gray-500 mb-2">Now in your resume (no longer a gap):</p>
                <div className="space-y-2">
                  {resolvedGapSkills.map((s) => (
                    <div key={s.skill_name} className="flex items-center justify-between border border-gray-800/60 bg-gray-800/30 rounded-xl px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                        <span className="text-gray-400 text-sm">{s.skill_name}</span>
                      </div>
                      <button onClick={() => handleDismiss(s.skill_name)} className="text-gray-600 hover:text-red-400" title="Remove">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
