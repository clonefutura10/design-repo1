import { useState, useCallback, useEffect, useRef } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { useNavigate } from "react-router-dom";
import {
  UploadCloud, FileText, Loader2, AlertCircle, Check,
  Database, Cpu, FileSearch, Layers, PenTool,
} from "lucide-react";
import { clsx } from "clsx";
import { annotate } from "../api/client";

// Action-oriented phases shown while the backend processes the PDF. The bar is
// indeterminate (we can't get true server progress over a single request), so
// we advance the highlight on an elapsed timer to show the engine is alive.
const PROCESS_PHASES = [
  "Reading pages & detecting forms",
  "Filtering EDC scaffolding noise",
  "Mapping fields to SDTM variables",
  "Writing FreeText annotations",
  "Finalising PDF & traceability export",
];
const MAX_UPLOAD_MB = 150;

const PIPELINE_STEPS = [
  {
    icon: Database,
    title: "Document & Standards Intake",
    color: "#6B2D88",
    bg: "#EDE0F5",
    desc: "Accepts blank CRF PDFs alongside SDTM standards, controlled terminology, and study-specific mappings to ground every decision in authoritative sources.",
  },
  {
    icon: Cpu,
    title: "Smart Knowledge Index",
    color: "#00699A",
    bg: "#E0F2FF",
    desc: "Builds a high-speed, structured knowledge base from your standards and specs so field lookups happen instantly at any scale.",
  },
  {
    icon: FileSearch,
    title: "Form Structure Recognition",
    color: "#00843D",
    bg: "#E6F6EC",
    desc: "Reads each page to identify CRF forms, visit folders, field labels, and data-entry patterns — filtering noise so only meaningful fields are passed forward.",
  },
  {
    icon: Layers,
    title: "Intelligent SDTM Mapping",
    color: "#E65100",
    bg: "#FFF3E0",
    desc: "Maps every extracted field to the correct SDTM domain, variable, codelist, and qualifier with high-confidence scoring and supplemental dataset support.",
  },
  {
    icon: PenTool,
    title: "Annotated CRF Generation",
    color: "#D32F2F",
    bg: "#FDEAEA",
    desc: "Produces a standards-compliant aCRF with colour-coded domain headers, extractable FreeText annotations, dataset bookmarks, and cross-page references.",
  },
];

export default function UploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // "upload" while bytes are in flight; "process" once the server is working.
  const [phase, setPhase] = useState<"upload" | "process">("upload");
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<number | null>(null);

  const onDrop = useCallback(
    (accepted: File[], rejections: FileRejection[]) => {
      setError(null);
      if (rejections.length > 0) {
        const r = rejections[0];
        const code = r.errors[0]?.code;
        if (code === "file-too-large") {
          const mb = (r.file.size / 1024 / 1024).toFixed(0);
          setError(`"${r.file.name}" is ${mb} MB — the limit is ${MAX_UPLOAD_MB} MB.`);
        } else if (code === "file-invalid-type") {
          setError(`"${r.file.name}" isn't a PDF. Please upload a CRF in PDF format.`);
        } else if (code === "too-many-files") {
          setError("Please upload one CRF PDF at a time.");
        } else {
          setError(r.errors[0]?.message ?? "That file could not be accepted.");
        }
        return;
      }
      if (accepted[0]) setFile(accepted[0]);
    },
    []
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    maxSize: MAX_UPLOAD_MB * 1024 * 1024,
  });

  // Drive the elapsed-time counter while processing so the user sees progress.
  useEffect(() => {
    if (loading && phase === "process") {
      timerRef.current = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    }
    return () => {
      if (timerRef.current) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [loading, phase]);

  // Advance the highlighted phase over time. Slows down near the end so it
  // never claims to be "finished" before the server actually responds.
  const activePhase = Math.min(
    PROCESS_PHASES.length - 1,
    Math.floor(elapsed / 6) + Math.floor(Math.max(0, elapsed - 24) / 15)
  );

  const handleSubmit = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setProgress(0);
    setElapsed(0);
    setPhase("upload");
    try {
      const { data } = await annotate(file, (pct) => {
        setProgress(pct);
        if (pct >= 100) setPhase("process");
      });
      navigate(`/jobs/${data.job_id}`, { state: data });
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e.message ?? "Unexpected error");
    } finally {
      setLoading(false);
      setPhase("upload");
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold" style={{ color: "#1A1A1A" }}>Annotate CRF</h1>
        <p className="mt-1 text-sm" style={{ color: "#6B6B6B" }}>
          Upload a blank CRF PDF and the engine will produce a fully annotated aCRF with SDTM variable mappings.
        </p>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={clsx(
          "border-2 border-dashed rounded-card p-10 text-center cursor-pointer transition-colors",
          isDragActive
            ? "border-az-primary bg-purple-50"
            : file
            ? "border-az-success bg-green-50"
            : "border-az-border hover:border-az-primary hover:bg-az-surface"
        )}
      >
        <input {...getInputProps()} />
        {file ? (
          <div className="flex flex-col items-center gap-3">
            <FileText className="w-12 h-12" style={{ color: "#00843D" }} />
            <p className="font-semibold" style={{ color: "#1A1A1A" }}>{file.name}</p>
            <p className="text-sm" style={{ color: "#6B6B6B" }}>{(file.size / 1024 / 1024).toFixed(2)} MB</p>
            <p className="text-xs" style={{ color: "#6B6B6B" }}>Drop a new file to replace</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <UploadCloud className="w-12 h-12" style={{ color: "#E5E5E5" }} />
            <p className="font-semibold" style={{ color: "#1A1A1A" }}>
              {isDragActive ? "Drop your PDF here" : "Drag & drop your blank CRF PDF"}
            </p>
            <p className="text-sm" style={{ color: "#6B6B6B" }}>or click to browse · PDF only · max 150 MB</p>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 rounded-card p-4 text-sm" style={{ background: "#FDEAEA", border: "1px solid #D32F2F", color: "#D32F2F" }}>
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Progress */}
      {loading && (
        <div className="rounded-card border border-az-border p-4" style={{ background: "#FFFFFF" }}>
          {phase === "upload" ? (
            <>
              <div className="flex justify-between text-xs mb-1" style={{ color: "#6B6B6B" }}>
                <span>Uploading “{file?.name}”…</span>
                <span>{progress}%</span>
              </div>
              <div className="w-full rounded-full h-2" style={{ background: "#E5E5E5" }}>
                <div
                  className="h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%`, background: "#6B2D88" }}
                />
              </div>
            </>
          ) : (
            <>
              <div className="flex justify-between text-xs mb-3" style={{ color: "#6B6B6B" }}>
                <span className="flex items-center gap-1.5">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: "#6B2D88" }} />
                  Processing on the server…
                </span>
                <span>{elapsed}s elapsed</span>
              </div>
              {/* Indeterminate bar */}
              <div className="w-full rounded-full h-1.5 overflow-hidden mb-4" style={{ background: "#EDE0F5" }}>
                <div className="h-1.5 rounded-full animate-pulse" style={{ width: "100%", background: "#6B2D88", opacity: 0.5 }} />
              </div>
              {/* Live staged checklist */}
              <ul className="space-y-2">
                {PROCESS_PHASES.map((label, i) => {
                  const done = i < activePhase;
                  const active = i === activePhase;
                  return (
                    <li key={i} className="flex items-center gap-2.5 text-sm">
                      <span
                        className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center"
                        style={{
                          background: done ? "#00843D" : active ? "#EDE0F5" : "#F2F2F2",
                          border: active ? "1px solid #6B2D88" : "none",
                        }}
                      >
                        {done ? (
                          <Check className="w-3 h-3 text-white" />
                        ) : active ? (
                          <Loader2 className="w-3 h-3 animate-spin" style={{ color: "#6B2D88" }} />
                        ) : (
                          <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#C4C4C4" }} />
                        )}
                      </span>
                      <span style={{ color: done || active ? "#1A1A1A" : "#9A9A9A", fontWeight: active ? 600 : 400 }}>
                        {label}
                      </span>
                    </li>
                  );
                })}
              </ul>
              <p className="text-xs mt-3" style={{ color: "#9A9A9A" }}>
                Large CRFs (hundreds of pages) can take a minute or two — this page will open the results automatically when done.
              </p>
            </>
          )}
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!file || loading}
        className="btn-primary w-full justify-center py-3 text-base"
      >
        {loading ? (
          <><Loader2 className="w-4 h-4 animate-spin" />Processing…</>
        ) : (
          <><UploadCloud className="w-4 h-4" />Generate Annotated CRF</>
        )}
      </button>

      {/* Pipeline Overview */}
      <div>
        <h2 className="text-base font-semibold mb-4" style={{ color: "#1A1A1A" }}>
          How It Works
        </h2>
        <div className="space-y-3">
          {PIPELINE_STEPS.map(({ icon: Icon, title, color, bg, desc }, i) => (
            <div
              key={i}
              className="rounded-card shadow-az border border-az-border p-4 flex gap-4"
              style={{ background: "#FFFFFF" }}
            >
              <div
                className="shrink-0 w-9 h-9 rounded-btn flex items-center justify-center"
                style={{ background: bg }}
              >
                <Icon className="w-4 h-4" style={{ color }} />
              </div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="text-xs font-bold rounded-full px-2 py-0.5"
                    style={{ background: bg, color }}
                  >
                    Step {i + 1}
                  </span>
                  <p className="text-sm font-semibold" style={{ color: "#1A1A1A" }}>{title}</p>
                </div>
                <p className="text-sm leading-relaxed" style={{ color: "#6B6B6B" }}>{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}