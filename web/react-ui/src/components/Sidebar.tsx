import { motion } from "framer-motion";
import { LayoutGrid, Folder, Globe, Zap, Settings, Shapes, Monitor } from "lucide-react";
import type { View } from "../lib/types";
import VoiceWidget from "./VoiceWidget";

const ITEMS: { id: View; label: string; Icon: typeof LayoutGrid; kbd: string }[] = [
  { id: "dashboard", label: "DASHBOARD", Icon: Shapes,     kbd: "01" },
  { id: "apps",      label: "APPS",      Icon: LayoutGrid, kbd: "02" },
  { id: "folders",   label: "FOLDERS",   Icon: Folder,     kbd: "03" },
  { id: "websites",  label: "WEBSITES",  Icon: Globe,      kbd: "04" },
  { id: "modes",     label: "MODES",     Icon: Zap,        kbd: "05" },
  { id: "browser",   label: "BROWSER",   Icon: Monitor,    kbd: "06" },
  { id: "settings",  label: "SETTINGS",  Icon: Settings,   kbd: "07" },
];

interface Props {
  view: View;
  setView: (v: View) => void;
  voice: boolean;
  setVoice: (v: boolean) => void;
}

export default function Sidebar({ view, setView, voice, setVoice }: Props) {
  return (
    <motion.aside
      initial={{ x: -40, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 180, damping: 24, delay: 0.1 }}
      className="relative z-10 w-52 xl:w-56 shrink-0 flex flex-col py-4"
    >
      <nav className="flex flex-col gap-1.5">
        {ITEMS.map((it, i) => {
          const active = view === it.id;
          return (
            <motion.button
              key={it.id}
              initial={{ opacity: 0, x: -24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.15 + i * 0.06, type: "spring", stiffness: 260, damping: 22 }}
              onClick={() => setView(it.id)}
              whileHover={{ x: active ? 0 : 5 }}
              whileTap={{ scale: 0.97 }}
              className={`group relative flex items-center gap-3 px-4 py-3.5 rounded-xl text-left cursor-pointer transition-colors duration-200 ${
                active ? "text-accent" : "text-zinc-400 hover:text-zinc-100"
              }`}
            >
              {active && (
                <motion.div
                  layoutId="nav-active"
                  transition={{ type: "spring", stiffness: 380, damping: 30 }}
                  className="absolute inset-0 rounded-xl bg-accent-10 border border-accent-25 shadow-[inset_0_0_22px_rgb(var(--accent)/0.1),0_0_22px_rgb(var(--accent)/0.12)]"
                />
              )}
              <it.Icon
                size={16}
                className={`relative z-10 transition-all duration-300 ${
                  active ? "drop-accent" : "group-hover:scale-115 group-hover:text-accent"
                }`}
              />
              <span className={`relative z-10 text-[12px] font-semibold tracking-[0.28em] ${active ? "text-glow" : ""}`}>
                {it.label}
              </span>
              <span
                className={`relative z-10 ml-auto font-mono2 text-[8px] tracking-widest transition-opacity duration-200 ${
                  active ? "text-accent/70 opacity-100" : "text-zinc-700 opacity-0 group-hover:opacity-100"
                }`}
              >
                {it.kbd}
              </span>
              {active && (
                <motion.span
                  layoutId="nav-dot"
                  className="absolute -left-1 top-1/2 -translate-y-1/2 w-1 h-6 rounded-full bg-accent shadow-glow-sm"
                />
              )}
            </motion.button>
          );
        })}
      </nav>

      <div className="flex-1" />

      <VoiceWidget active={voice} onToggle={() => setVoice(!voice)} />

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.8 }}
        className="mx-1 mt-3 px-3 py-2.5 flex items-center gap-2.5 border-t border-white/5"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-accent breathe shadow-glow-sm" />
        <div>
          <div className="font-mono2 text-[9px] tracking-[0.24em] text-accent/80">NaiTRO OS 2.0.1</div>
          <div className="font-mono2 text-[8px] tracking-[0.2em] text-zinc-600">BUILD 2026.05.16</div>
        </div>
      </motion.div>
    </motion.aside>
  );
}
