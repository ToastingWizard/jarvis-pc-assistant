import { Target, Briefcase, Clapperboard, Code } from "lucide-react";
import Tilt from "./Tilt";
import Reveal from "./Reveal";
import type { ModeInfo } from "../lib/api";

/* Real modes come from the config as name/steps/style — no stored icon, so
   cycle a fixed set by grid position. */
const MODE_ICONS = [Target, Briefcase, Clapperboard, Code];

interface Props {
  mode: ModeInfo;
  i: number;
  active: boolean;
  big?: boolean;
  base?: number;
  onToggle: () => void;
  onDelete?: () => void;
}

export default function ModeCard({ mode, i, active, big = false, base = 0.1, onToggle, onDelete }: Props) {
  const Icon = MODE_ICONS[i % MODE_ICONS.length];
  const detail = mode.style || (mode.steps.length > 0 ? mode.steps.map((s) => s.name || s.url).join(" · ") : "Routine mode");

  return (
    <Reveal i={i} base={base}>
      <Tilt max={8} scale={1.03} onClick={onToggle} className="cursor-pointer group">
        <div className={`relative rounded-2xl p-px overflow-hidden ${active ? "" : "border border-white/[0.07] bg-white/[0.015] group-hover:border-accent-25"}`}>
          {active && (
            <div
              className="absolute inset-[-160%] sp"
              style={{
                ["--dur" as string]: "3.2s",
                background: "conic-gradient(transparent 0deg 200deg, rgb(var(--accent) / 0.25) 260deg, rgb(var(--accent)) 320deg, transparent 360deg)",
              }}
            />
          )}
          {onDelete && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              title="Delete mode"
              className="absolute top-2 right-2 z-10 font-mono2 text-[9px] text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
            >
              ✕
            </button>
          )}
          <div
            className={`relative rounded-[15px] transition-colors duration-300 ${
              active ? "bg-[#0c0518]/95 shadow-[inset_0_0_30px_rgb(var(--accent)/0.08)]" : "bg-black/20"
            } ${big ? "p-5 h-full" : "p-4"} flex items-center gap-4`}
          >
            <div
              className={`grid place-items-center rounded-xl border transition-all duration-300 shrink-0 ${
                big ? "w-12 h-12" : "w-10 h-10"
              } ${
                active
                  ? "border-accent-40 bg-accent-15 text-accent shadow-glow-sm"
                  : "border-white/10 bg-white/[0.03] text-zinc-400 group-hover:text-accent group-hover:border-accent-25"
              }`}
            >
              <Icon size={big ? 21 : 17} />
            </div>
            <div className="min-w-0 flex-1">
              <div className={`font-semibold tracking-[0.18em] ${big ? "text-[13px]" : "text-[12px]"} ${active ? "text-white" : "text-zinc-200"}`}>
                {mode.name}
              </div>
              <div className="text-[11px] text-zinc-500 mt-0.5">{mode.desc}</div>
              {big && <div className="text-[11px] leading-5 text-zinc-600 mt-2.5 truncate">{detail}</div>}
            </div>
            <div className="flex flex-col items-center gap-1.5 shrink-0">
              <span
                className={`w-2.5 h-2.5 rounded-full transition-all duration-300 ${
                  active ? "bg-accent shadow-glow-sm breathe" : "border border-zinc-700 group-hover:border-accent-40"
                }`}
              />
              {big && (
                <span className={`font-mono2 text-[8px] tracking-[0.26em] ${active ? "text-accent" : "text-zinc-700"}`}>
                  {active ? "ONLINE" : "IDLE"}
                </span>
              )}
            </div>
          </div>
        </div>
      </Tilt>
    </Reveal>
  );
}
