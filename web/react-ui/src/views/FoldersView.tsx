import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Folder, ChevronRight, ArrowLeft, Plus, FileText, FileImage, FileVideo,
  FileArchive, FileAudio, FileCode2, File as FileIcon,
} from "lucide-react";
import { FOLDER_FILES, type FileKind } from "../lib/data";
import type { Ctx } from "../lib/types";
import Reveal from "../components/Reveal";
import Tilt from "../components/Tilt";

const KIND_META: Record<FileKind, { Icon: typeof FileText; color: string }> = {
  doc:  { Icon: FileText,    color: "#93c5fd" },
  img:  { Icon: FileImage,   color: "#f0abfc" },
  vid:  { Icon: FileVideo,   color: "#fda4af" },
  arc:  { Icon: FileArchive, color: "#fcd34d" },
  aud:  { Icon: FileAudio,   color: "#6ee7b7" },
  code: { Icon: FileCode2,   color: "#a78bfa" },
  file: { Icon: FileIcon,    color: "#a1a1aa" },
};

const FALLBACK_FILES = [
  { name: "notes.txt", size: "1 KB", date: "TODAY", kind: "doc" as FileKind },
  { name: "untitled.png", size: "64 KB", date: "TODAY", kind: "img" as FileKind },
];

export default function FoldersView({ ctx }: { ctx: Ctx }) {
  const [open, setOpen] = useState<{ id: string; name: string; color: string } | null>(null);
  const files = open ? FOLDER_FILES[open.id] ?? FALLBACK_FILES : [];

  return (
    <div className="flex flex-col h-full min-h-0">
      <Reveal i={0} className="flex items-center justify-between gap-4 mb-5 shrink-0">
        <div>
          <div className="flex items-center gap-2 font-mono2 text-[10px] tracking-[0.26em] text-zinc-500">
            <button
              onClick={() => setOpen(null)}
              className={`hover:text-accent transition-colors cursor-pointer ${open ? "" : "text-accent"}`}
            >
              ROOT
            </button>
            {open && (
              <>
                <ChevronRight size={11} className="text-zinc-700" />
                <motion.span
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="text-accent text-glow uppercase"
                >
                  {open.name}
                </motion.span>
              </>
            )}
          </div>
          <h1 className="font-orbitron text-xl font-bold tracking-[0.3em] grad-text mt-2 flex items-center gap-3">
            {open ? open.name.toUpperCase() : "FILE VAULT"}
            {open && (
              <span className="font-mono2 text-[9px] tracking-[0.24em] px-2 py-1 rounded-md border border-accent-25 bg-accent-10 text-accent">
                {files.length} OBJECTS
              </span>
            )}
          </h1>
        </div>
        <div className="flex items-center gap-3">
          {open && (
            <motion.button
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setOpen(null)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-white/10 text-zinc-300 text-[10px] font-semibold tracking-[0.26em] hover:border-accent-40 hover:text-accent transition-colors cursor-pointer"
            >
              <ArrowLeft size={13} /> BACK
            </motion.button>
          )}
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => ctx.openAdd("folders")}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-accent-15 border border-accent-40 text-accent text-[10px] font-semibold tracking-[0.26em] hover:shadow-glow transition-shadow cursor-pointer"
          >
            <Plus size={13} /> NEW
          </motion.button>
        </div>
      </Reveal>

      <div className="jscroll flex-1 min-h-0 overflow-y-auto pr-1 pb-2">
        <AnimatePresence mode="wait">
          {!open ? (
            <motion.div
              key="grid"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, x: -24, transition: { duration: 0.18 } }}
              className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-4 pt-2"
            >
              {ctx.folders.map((f, i) => (
                <Reveal key={f.id} i={i} base={0.04}>
                  <Tilt max={10} scale={1.04} onClick={() => { setOpen(f); ctx.runAction("folder", f.name); }} className="glass-panel !rounded-2xl p-5 flex flex-col items-center gap-3 cursor-pointer">
                    <div className="relative">
                      <div className="absolute inset-0 rounded-2xl blur-xl opacity-0 group-hover:opacity-60 transition-opacity duration-300" style={{ background: `${f.color}55` }} />
                      <Folder size={52} strokeWidth={1.1} style={{ color: f.color }} className="relative transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-3" />
                    </div>
                    <div className="text-center">
                      <div className="text-[12px] font-semibold tracking-[0.14em] text-zinc-200">{f.name}</div>
                      <div className="font-mono2 text-[8px] tracking-[0.2em] text-zinc-600 mt-1">
                        {(FOLDER_FILES[f.id] ?? FALLBACK_FILES).length} OBJECTS
                      </div>
                    </div>
                    {f.custom && (
                      <button
                        onClick={(e) => { e.stopPropagation(); ctx.removeExtra("folders", f.id); ctx.pushToast("Folder removed", f.name); }}
                        className="absolute top-2 right-2 font-mono2 text-[9px] text-zinc-600 hover:text-red-400 cursor-pointer"
                      >
                        ✕
                      </button>
                    )}
                  </Tilt>
                </Reveal>
              ))}
            </motion.div>
          ) : (
            <motion.div
              key="files"
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 24, transition: { duration: 0.18 } }}
              className="glass-panel !rounded-2xl overflow-hidden mt-2"
            >
              <div className="grid grid-cols-[1fr_90px_110px] gap-2 px-5 py-3 border-b border-white/5 font-mono2 text-[9px] tracking-[0.3em] text-zinc-500">
                <span>NAME</span><span>SIZE</span><span>MODIFIED</span>
              </div>
              {files.map((f, i) => {
                const M = KIND_META[f.kind];
                return (
                  <motion.button
                    key={f.name}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05, type: "spring", stiffness: 280, damping: 24 }}
                    onClick={() => ctx.pushToast("Opening " + f.name, "Preview engine warming up…")}
                    className="w-full grid grid-cols-[1fr_90px_110px] gap-2 px-5 py-3.5 items-center text-left border-b border-white/[0.04] hover:bg-accent-5 transition-colors duration-150 group cursor-pointer"
                  >
                    <span className="flex items-center gap-3 min-w-0">
                      <M.Icon size={16} style={{ color: M.color }} className="shrink-0 transition-transform duration-200 group-hover:scale-125 group-hover:-rotate-6" />
                      <span className="text-[12px] font-medium tracking-[0.06em] text-zinc-300 group-hover:text-white truncate">{f.name}</span>
                    </span>
                    <span className="font-mono2 text-[10px] text-zinc-500">{f.size}</span>
                    <span className="font-mono2 text-[10px] text-zinc-600">{f.date}</span>
                  </motion.button>
                );
              })}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
