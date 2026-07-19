import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Folder, Sparkles } from "lucide-react";
import { APP_ICON_CHOICES, SWATCHES } from "../lib/data";
import type { AddKind, ExtraItem } from "../lib/types";

const LABELS: Record<AddKind, string> = { apps: "APPLICATION", folders: "FOLDER", sites: "WEBSITE" };

interface Props {
  kind: AddKind | null;
  onClose: () => void;
  onSubmit: (kind: AddKind, item: ExtraItem) => void;
}

export default function AddItemModal({ kind, onClose, onSubmit }: Props) {
  const [name, setName] = useState("");
  const [color, setColor] = useState(SWATCHES[0]);
  const [icon, setIcon] = useState(0);

  useEffect(() => {
    setName(""); setColor(SWATCHES[0]); setIcon(0);
  }, [kind]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const submit = () => {
    if (!kind || !name.trim()) return;
    onSubmit(kind, { id: `x-${Date.now()}`, name: name.trim(), color, icon });
    onClose();
  };

  const Preview = () => {
    if (kind === "apps") {
      const Ic = APP_ICON_CHOICES[icon];
      return <Ic size={26} style={{ color }} />;
    }
    if (kind === "folders") return <Folder size={26} strokeWidth={1.4} style={{ color }} />;
    return (
      <span
        className="grid place-items-center w-10 h-10 rounded-xl font-orbitron font-bold text-lg"
        style={{ background: `${color}26`, border: `1px solid ${color}66`, color, textShadow: `0 0 12px ${color}` }}
      >
        {(name.trim() || "?").charAt(0).toUpperCase()}
      </span>
    );
  };

  return (
    <AnimatePresence>
      {kind && (
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
            className="glass-panel w-[min(92vw,420px)] p-6"
          >
            <span className="corner corner-tl" /><span className="corner corner-tr" />
            <span className="corner corner-bl" /><span className="corner corner-br" />

            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2.5">
                <Sparkles size={14} className="text-accent drop-accent" />
                <h3 className="panel-title">NEW {LABELS[kind]}</h3>
              </div>
              <button
                onClick={onClose}
                className="grid place-items-center w-7 h-7 rounded-lg text-zinc-500 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
              >
                <X size={14} />
              </button>
            </div>

            <div className="flex items-center gap-4 mb-5">
              <div className="grid place-items-center w-16 h-16 rounded-2xl border border-accent-25 bg-accent-10 shadow-glow-sm shrink-0">
                <Preview />
              </div>
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder={`${LABELS[kind]} NAME`}
                className="jtext flex-1 px-3.5 py-2.5 text-[13px] tracking-[0.12em] font-semibold"
              />
            </div>

            {kind === "apps" && (
              <div className="mb-5">
                <div className="font-mono2 text-[9px] tracking-[0.3em] text-zinc-500 mb-2.5">GLYPH</div>
                <div className="grid grid-cols-8 gap-1.5">
                  {APP_ICON_CHOICES.map((Ic, i) => (
                    <button
                      key={i}
                      onClick={() => setIcon(i)}
                      className={`grid place-items-center aspect-square rounded-lg border transition-all duration-150 cursor-pointer hover:scale-110 ${
                        icon === i ? "border-accent-60 bg-accent-15 text-accent shadow-glow-sm" : "border-white/10 text-zinc-500 hover:text-zinc-200"
                      }`}
                    >
                      <Ic size={14} />
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mb-6">
              <div className="font-mono2 text-[9px] tracking-[0.3em] text-zinc-500 mb-2.5">SIGNATURE COLOR</div>
              <div className="flex gap-2 flex-wrap">
                {SWATCHES.map((c) => (
                  <button
                    key={c}
                    onClick={() => setColor(c)}
                    className={`w-7 h-7 rounded-lg transition-all duration-150 cursor-pointer hover:scale-115 ${
                      color === c ? "scale-115 ring-2 ring-white/60" : "opacity-70 hover:opacity-100"
                    }`}
                    style={{ background: c, boxShadow: color === c ? `0 0 14px ${c}` : "none" }}
                  />
                ))}
              </div>
            </div>

            <button
              onClick={submit}
              disabled={!name.trim()}
              className="w-full py-3 rounded-xl bg-accent-15 border border-accent-40 text-accent font-semibold text-[11px] tracking-[0.34em] hover:bg-accent-20 hover:shadow-glow transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
            >
              CREATE SHORTCUT
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
