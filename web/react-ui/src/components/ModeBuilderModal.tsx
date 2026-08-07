import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Sparkles, Plus, ChevronUp, ChevronDown, AppWindow, Globe, Folder, Music } from "lucide-react";
import { naitroApi, type ActionResult, type ModeInfo, type ModeStep } from "../lib/api";

const STEP_LABELS: Record<ModeStep["type"], string> = {
  app: "APPLICATION",
  website: "WEBSITE",
  folder: "FOLDER",
  playlist: "PLAYLIST",
};

const STEP_ICONS: Record<ModeStep["type"], typeof AppWindow> = {
  app: AppWindow,
  website: Globe,
  folder: Folder,
  playlist: Music,
};

const PICKER_KEY: Record<ModeStep["type"], keyof Props["picker"]> = {
  app: "apps",
  website: "websites",
  folder: "folders",
  playlist: "playlists",
};

/* Used so the builder still works in the no-backend preview. */
const FALLBACK_OPTIONS: Record<ModeStep["type"], string[]> = {
  app: ["notepad", "chrome", "spotify"],
  website: ["youtube", "netflix", "google"],
  folder: ["downloads", "documents"],
  playlist: ["liked songs"],
};

interface Props {
  mode: ModeInfo | null | undefined; // undefined = closed, null = new
  onClose: () => void;
  onSaved: (res: ActionResult | null, name: string) => void;
  picker: { apps: string[]; websites: string[]; folders: string[]; playlists: string[] };
}

export default function ModeBuilderModal({ mode, onClose, onSaved, picker }: Props) {
  const open = mode !== undefined;

  const [name, setName] = useState("");
  const [style, setStyle] = useState("");
  const [steps, setSteps] = useState<ModeStep[]>([]);
  const [stepType, setStepType] = useState<ModeStep["type"]>("app");
  const [stepName, setStepName] = useState("");
  const [stepUrl, setStepUrl] = useState("");
  const [stepDelay, setStepDelay] = useState("");

  /* Reset the form each time the modal opens (edit populates, new is blank). */
  useEffect(() => {
    if (open) {
      setName(mode?.name ?? "");
      setStyle(mode?.style ?? "");
      setSteps(mode?.steps ?? []);
      setStepType("app");
      setStepName("");
      setStepUrl("");
      setStepDelay("");
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const options = picker[PICKER_KEY[stepType]].length
    ? picker[PICKER_KEY[stepType]]
    : FALLBACK_OPTIONS[stepType];

  const addStep = () => {
    const custom = stepName.trim() || stepUrl.trim();
    if (!custom) return;
    const step: ModeStep = { type: stepType };
    if (stepType === "website") {
      step.url = stepUrl.trim() || stepName.trim();
    } else {
      step.name = stepName.trim();
    }
    const d = Number(stepDelay);
    if (stepDelay.trim() && !Number.isNaN(d) && d > 0) step.delay = d;
    setSteps((s) => [...s, step]);
    setStepName("");
    setStepUrl("");
    setStepDelay("");
  };

  const move = (i: number, dir: -1 | 1) => {
    setSteps((s) => {
      const j = i + dir;
      if (j < 0 || j >= s.length) return s;
      const next = [...s];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  };

  const canSave = name.trim().length > 0 && (steps.length > 0 || style.trim().length > 0);

  const submit = async () => {
    if (!canSave) return;
    const res = await naitroApi.saveMode(name.trim(), steps, style.trim());
    onSaved(res, name.trim());
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] grid place-items-center bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.86, y: 26 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 16 }}
            transition={{ type: "spring", stiffness: 340, damping: 26 }}
            onClick={(e) => e.stopPropagation()}
            className="glass-panel w-[min(94vw,560px)] p-6"
          >
            <span className="corner corner-tl" /><span className="corner corner-tr" />
            <span className="corner corner-bl" /><span className="corner corner-br" />

            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2.5">
                <Sparkles size={14} className="text-accent drop-accent" />
                <h3 className="panel-title">{mode ? "EDIT MODE" : "MODE FORGE"}</h3>
              </div>
              <button
                onClick={onClose}
                className="grid place-items-center w-7 h-7 rounded-lg text-zinc-500 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
              >
                <X size={14} />
              </button>
            </div>

            <div className="jscroll max-h-[72vh] overflow-y-auto pr-1">
              {/* name */}
              <div className="mb-4">
                <div className="font-mono2 text-[9px] tracking-[0.3em] text-zinc-500 mb-2">MODE NAME</div>
                <input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                  placeholder="e.g. study mode"
                  className="jtext w-full px-3.5 py-2.5 text-[13px] tracking-[0.12em] font-semibold"
                />
              </div>

              {/* AI personality */}
              <div className="mb-4">
                <div className="font-mono2 text-[9px] tracking-[0.3em] text-zinc-500 mb-2">AI PERSONALITY <span className="text-zinc-700">(OPTIONAL)</span></div>
                <textarea
                  value={style}
                  onChange={(e) => setStyle(e.target.value)}
                  placeholder="How should NaiTRO talk in this mode? e.g. calm, methodical study partner"
                  rows={2}
                  className="jtext w-full px-3.5 py-2.5 text-[12px] tracking-[0.06em] resize-none"
                />
              </div>

              {/* routine steps */}
              <div className="mb-4">
                <div className="font-mono2 text-[9px] tracking-[0.3em] text-zinc-500 mb-2">ROUTINE STEPS</div>

                <div className="grid grid-cols-4 gap-1.5 mb-3">
                  {(Object.keys(STEP_LABELS) as ModeStep["type"][]).map((t) => {
                    const Ic = STEP_ICONS[t];
                    return (
                      <button
                        key={t}
                        onClick={() => setStepType(t)}
                        className={`flex flex-col items-center gap-1.5 py-2 rounded-lg border transition-all duration-150 cursor-pointer hover:scale-[1.03] ${
                          stepType === t ? "border-accent-60 bg-accent-15 text-accent shadow-glow-sm" : "border-white/10 text-zinc-500 hover:text-zinc-200"
                        }`}
                      >
                        <Ic size={14} />
                        <span className="font-mono2 text-[8px] tracking-[0.2em]">{STEP_LABELS[t]}</span>
                      </button>
                    );
                  })}
                </div>

                <select
                  value={stepName}
                  onChange={(e) => setStepName(e.target.value)}
                  className="jtext w-full px-3 py-2 text-[12px] tracking-[0.1em] mb-2"
                >
                  <option value="">SELECT {STEP_LABELS[stepType]}…</option>
                  {options.map((o) => (
                    <option key={o} value={o}>{o}</option>
                  ))}
                </select>

                <div className="flex gap-2 mb-2">
                  <input
                    value={stepName}
                    onChange={(e) => setStepName(e.target.value)}
                    placeholder="or type a name"
                    className="jtext flex-1 px-3 py-2 text-[12px] tracking-[0.1em]"
                  />
                  {stepType === "website" && (
                    <input
                      value={stepUrl}
                      onChange={(e) => setStepUrl(e.target.value)}
                      placeholder="url (optional)"
                      className="jtext flex-1 px-3 py-2 text-[12px] tracking-[0.1em]"
                    />
                  )}
                  <input
                    value={stepDelay}
                    onChange={(e) => setStepDelay(e.target.value)}
                    placeholder="delay s"
                    type="number"
                    min={0}
                    className="jtext w-20 px-2 py-2 text-[12px] tracking-[0.1em]"
                  />
                  <button
                    onClick={addStep}
                    disabled={!(stepName.trim() || stepUrl.trim())}
                    className="flex items-center gap-1 px-3 py-2 rounded-lg bg-accent-15 border border-accent-40 text-accent text-[10px] font-semibold tracking-[0.2em] hover:shadow-glow transition-shadow disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer shrink-0"
                  >
                    <Plus size={12} /> ADD
                  </button>
                </div>

                {steps.length > 0 && (
                  <div className="flex flex-col gap-1.5">
                    {steps.map((s, i) => {
                      const Ic = STEP_ICONS[s.type];
                      return (
                        <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 bg-white/[0.02]">
                          <Ic size={13} className="text-accent shrink-0" />
                          <span className="text-[12px] font-medium tracking-[0.08em] text-zinc-200 flex-1 min-w-0 truncate">
                            {s.name || s.url}
                          </span>
                          <span className="font-mono2 text-[9px] text-zinc-600">{STEP_LABELS[s.type]}</span>
                          {s.delay != null && <span className="font-mono2 text-[9px] text-accent">+{s.delay}s</span>}
                          <button onClick={() => move(i, -1)} className="text-zinc-600 hover:text-white transition-colors cursor-pointer"><ChevronUp size={13} /></button>
                          <button onClick={() => move(i, 1)} className="text-zinc-600 hover:text-white transition-colors cursor-pointer"><ChevronDown size={13} /></button>
                          <button
                            onClick={() => setSteps((x) => x.filter((_, j) => j !== i))}
                            className="text-zinc-600 hover:text-red-400 transition-colors cursor-pointer"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            <button
              onClick={submit}
              disabled={!canSave}
              className="w-full py-3 rounded-xl bg-accent-15 border border-accent-40 text-accent font-semibold text-[11px] tracking-[0.34em] hover:bg-accent-20 hover:shadow-glow transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >
              {mode ? "UPDATE MODE" : "FORGE MODE"}
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
