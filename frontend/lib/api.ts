"use client";

const API = "/backend";

async function authFetch(token: string, path: string, init: RequestInit = {}) {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    const msg = err.detail ?? err.message ?? "Request failed";
    throw new Error(`[${res.status}] ${msg}`);
  }
  return res.json();
}

// ── Resume ────────────────────────────────────────────────────────────────────
export async function uploadResume(token: string, file: File) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API}/resume/upload-file`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  if (!res.ok) {
    const raw = await res.text().catch(() => res.statusText);
    console.error("uploadResume raw error:", res.status, raw);
    let detail = raw;
    try { const j = JSON.parse(raw); detail = j.detail ?? j.message ?? raw; } catch {}
    throw new Error(`[${res.status}] ${detail}`);
  }
  return res.json();
}

export async function uploadResumeText(token: string, text: string, filename?: string) {
  return authFetch(token, "/resume/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, filename: filename?.trim() || "pasted-resume.txt" }),
  });
}

export async function listResumes(token: string) {
  return authFetch(token, "/users/me/resumes");
}

export async function deleteResume(token: string, resumeId: string) {
  return authFetch(token, `/users/me/resumes/${resumeId}`, { method: "DELETE" });
}

export async function setActiveResume(token: string, resumeId: string) {
  return authFetch(token, `/users/me/resumes/${resumeId}/activate`, { method: "POST" });
}

export async function renameResume(token: string, resumeId: string, filename: string) {
  return authFetch(token, `/users/me/resumes/${resumeId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename }),
  });
}

// ── Job Description ───────────────────────────────────────────────────────────
export async function uploadJD(token: string, text: string) {
  return authFetch(token, "/job/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

// ── Analysis ──────────────────────────────────────────────────────────────────
export async function runAnalysis(
  token: string,
  resumeId: string,
  jdId: string,
  weights?: { keyword: number; semantic: number; category: number }
) {
  return authFetch(token, "/analysis/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      resume_id: resumeId,
      jd_id: jdId,
      weights: weights ?? { keyword: 0.5, semantic: 0.3, category: 0.2 },
    }),
  });
}

export async function getAnalysis(token: string, analysisId: string) {
  return authFetch(token, `/analysis/${analysisId}`);
}

// ── Skills / Progress ─────────────────────────────────────────────────────────
export async function getSkillProgress(token: string) {
  return authFetch(token, "/users/me/skills");
}

export async function getResumeSkills(token: string) {
  return authFetch(token, "/users/me/resume-skills");
}

export async function clearSkillProgress(token: string) {
  return authFetch(token, "/users/me/skills", { method: "DELETE" });
}

export async function removeSkillProgress(token: string, skillName: string) {
  return authFetch(token, `/users/me/skills/${encodeURIComponent(skillName)}`, { method: "DELETE" });
}

export async function getHistory(token: string) {
  return authFetch(token, "/users/me/history");
}

// ── Feedback ───────────────────────────────────────────────────────────────────
export async function submitFeedback(token: string, category: string, message: string) {
  return authFetch(token, "/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category, message }),
  });
}

export async function getMyFeedback(token: string) {
  return authFetch(token, "/users/me/feedback");
}

// ── Quiz ──────────────────────────────────────────────────────────────────────
export async function startQuiz(token: string, analysisId: string, skill: string, difficulty: string) {
  return authFetch(token, `/quiz/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis_id: analysisId, skill, difficulty }),
  });
}

export async function submitQuiz(token: string, quizId: string, answers: Record<number, string>) {
  const orderedAnswers = Object.keys(answers)
    .map(Number)
    .sort((a, b) => a - b)
    .map((questionId) => {
      const fullOption = answers[questionId] ?? "";
      const letterMatch = fullOption.match(/^([A-D])\)/);
      return { answer: letterMatch ? letterMatch[1] : fullOption };
    });
  return authFetch(token, `/quiz/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quiz_id: quizId, answers: orderedAnswers }),
  });
}
