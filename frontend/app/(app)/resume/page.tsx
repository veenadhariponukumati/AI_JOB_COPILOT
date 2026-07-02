"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { uploadResume, uploadResumeText, listResumes, deleteResume, setActiveResume, renameResume } from "@/lib/api";
import { Upload, FileText, Loader2, CheckCircle, Trash2, ClipboardPaste, AlertTriangle, Pencil, Check, X } from "lucide-react";

type StoredResume = {
  resume_id: string;
  filename?: string;
  char_count?: number;
  upload_timestamp?: string;
  is_active?: boolean;
};

export default function MyResumePage() {
  const { getToken } = useAuth();
  const [resumes, setResumes] = useState<StoredResume[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [mode, setMode] = useState<"file" | "text">("file");
  const [pastedText, setPastedText] = useState("");
  const [pastedName, setPastedName] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  async function load() {
    setLoading(true);
    try {
      const token = await getToken();
      if (!token) return;
      const data = await listResumes(token);
      const list: StoredResume[] = Array.isArray(data) ? data : (data.resumes ?? []);
      setResumes(list);
    } catch (err: unknown) {
      setError("Failed to load resumes: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    setSuccess("Uploading and extracting skills from your resume...");
    try {
      const token = await getToken();
      await uploadResume(token!, file);
      setSuccess("Resume uploaded and set as active. Skills extracted and saved to My Skill Validation.");
      await load();
    } catch (err: unknown) {
      setError("Upload failed: " + (err instanceof Error ? err.message : String(err)));
      setSuccess("");
    } finally {
      setUploading(false);
    }
  }

  async function handleTextUpload() {
    if (!pastedText.trim()) return;
    setUploading(true);
    setError("");
    setSuccess("Saving resume and extracting skills...");
    try {
      const token = await getToken();
      await uploadResumeText(token!, pastedText, pastedName);
      setPastedText("");
      setPastedName("");
      setSuccess("Resume saved and set as active. Skills extracted and saved to My Skill Validation.");
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setSuccess("");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this resume?")) return;
    try {
      const token = await getToken();
      await deleteResume(token!, id);
      setSuccess("Resume deleted.");
      await load();
    } catch {
      setError("Delete failed.");
    }
  }

  async function handleActivate(id: string) {
    setActivatingId(id);
    setError("");
    try {
      const token = await getToken();
      await setActiveResume(token!, id);
      setSuccess("Active resume updated.");
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to set active resume.");
    } finally {
      setActivatingId(null);
    }
  }

  function startRename(r: StoredResume) {
    setRenamingId(r.resume_id);
    setRenameValue(r.filename ?? "");
  }

  async function submitRename(id: string) {
    if (!renameValue.trim()) return;
    try {
      const token = await getToken();
      await renameResume(token!, id, renameValue.trim());
      setRenamingId(null);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Rename failed.");
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-2">My Resume</h1>
      <p className="text-gray-400 text-sm mb-8">
        Upload your base resume once. The Analyze page can use it directly without re-uploading each time.
      </p>

      {/* Upload card */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-semibold">Upload Resume</h2>
          <div className="flex bg-gray-800 rounded-lg p-0.5 text-xs">
            <button
              onClick={() => setMode("file")}
              className={`px-3 py-1 rounded-md transition-colors ${mode === "file" ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200"}`}
            >
              PDF
            </button>
            <button
              onClick={() => setMode("text")}
              className={`px-3 py-1 rounded-md transition-colors ${mode === "text" ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200"}`}
            >
              Paste Text
            </button>
          </div>
        </div>

        {mode === "file" ? (
          <label className="block cursor-pointer">
            <div className="border-2 border-dashed border-gray-700 hover:border-indigo-500 rounded-xl p-10 text-center transition-colors">
              {uploading ? (
                <Loader2 className="w-8 h-8 text-indigo-400 mx-auto mb-2 animate-spin" />
              ) : (
                <Upload className="w-8 h-8 text-gray-600 mx-auto mb-2" />
              )}
              <p className="text-gray-400 text-sm">{uploading ? "Uploading and extracting skills..." : "Drop your PDF here or click to browse"}</p>
              <p className="text-gray-600 text-xs mt-1">PDF only</p>
            </div>
            <input type="file" accept=".pdf" className="hidden" onChange={handleFileUpload} disabled={uploading} />
          </label>
        ) : (
          <div>
            <input
              className="w-full mb-3 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-indigo-500"
              placeholder="Name this resume (optional, e.g. 'Backend-focused resume')"
              value={pastedName}
              onChange={(e) => setPastedName(e.target.value)}
            />
            <textarea
              className="w-full h-48 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-200 placeholder-gray-500 resize-none focus:outline-none focus:border-indigo-500"
              placeholder="Paste your full resume text here..."
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
            />
            <button
              onClick={handleTextUpload}
              disabled={!pastedText.trim() || uploading}
              className="mt-3 w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium rounded-xl flex items-center justify-center gap-2 transition-colors"
            >
              {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ClipboardPaste className="w-4 h-4" />}
              {uploading ? "Saving..." : "Save Resume"}
            </button>
          </div>
        )}

        {/* Feedback */}
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

      {/* Saved resumes */}
      <div>
        <h2 className="text-white font-semibold mb-1">Saved Resumes</h2>
        <p className="text-gray-500 text-xs mb-4">The active resume is used by Analyze and My Skill Validation. Click "Set Active" to switch.</p>
        {loading ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading...
          </div>
        ) : resumes.length === 0 ? (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 text-center">
            <FileText className="w-8 h-8 text-gray-700 mx-auto mb-3" />
            <p className="text-gray-500 text-sm">No resumes uploaded yet.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {resumes.map((r) => (
              <div key={r.resume_id} className="bg-gray-900 border border-gray-800 rounded-2xl px-5 py-4 flex items-center gap-4">
                <FileText className="w-5 h-5 text-indigo-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  {renamingId === r.resume_id ? (
                    <div className="flex items-center gap-2">
                      <input
                        autoFocus
                        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") submitRename(r.resume_id); if (e.key === "Escape") setRenamingId(null); }}
                      />
                      <button onClick={() => submitRename(r.resume_id)} className="text-emerald-400 hover:text-emerald-300"><Check className="w-4 h-4" /></button>
                      <button onClick={() => setRenamingId(null)} className="text-gray-500 hover:text-gray-300"><X className="w-4 h-4" /></button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <p className="text-white text-sm font-medium truncate">{r.filename ?? "Untitled resume"}</p>
                      <button onClick={() => startRename(r)} className="text-gray-700 hover:text-gray-400 transition-colors shrink-0" title="Rename">
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                  <div className="flex gap-3 mt-0.5">
                    {r.char_count !== undefined && (
                      <span className="text-gray-500 text-xs">{r.char_count.toLocaleString()} chars</span>
                    )}
                    {r.upload_timestamp && (
                      <span className="text-gray-600 text-xs">{new Date(r.upload_timestamp).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
                {r.is_active ? (
                  <span className="text-xs text-indigo-400 bg-indigo-950/50 border border-indigo-800/40 px-2 py-0.5 rounded-full shrink-0">Active</span>
                ) : (
                  <button
                    onClick={() => handleActivate(r.resume_id)}
                    disabled={activatingId === r.resume_id}
                    className="text-xs text-gray-400 hover:text-indigo-400 border border-gray-700 hover:border-indigo-600 px-2 py-1 rounded-full shrink-0 transition-colors disabled:opacity-40"
                  >
                    {activatingId === r.resume_id ? "Setting..." : "Set Active"}
                  </button>
                )}
                <button
                  onClick={() => handleDelete(r.resume_id)}
                  className="text-gray-700 hover:text-red-400 transition-colors shrink-0"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
