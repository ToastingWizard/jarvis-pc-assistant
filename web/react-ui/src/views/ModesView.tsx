import { Zap, Power } from "lucide-react";
import { MODES } from "../lib/data";
import type { Ctx } from "../lib/types";
import ModeCard from "../components/ModeCard";
import Reveal from "../components/Reveal";

export default function ModesView({ ctx }: { ctx: Ctx }) {
  const active = MODES.find((m) => m.id === ctx.activeMode);

  return (
    <div className="flex flex-col h-full min-h-0">
      <Reveal i={0} className="flex items-center justify-between gap-4 mb-6 shrink-0">
        <div>
          <div className="flex items-center gap-3">
            <Zap size={18} className="text-accent drop-accent" />
            <h1 className="font-orbitron text-xl font-bold tracking-[0.3em] grad-text">SYSTEM MODES</h1>
            <span className={`font-mono2 text-[9px] tracking-[0.24em] px-2 py-1 rounded-md border transition-all duration-300 ${
              active ? "border-accent-40 bg-accent-15 text-accent shadow-glow-sm" : "border-white/10 text-zinc-500"
            }`}>
              {active ? active.name : "BASELINE"}
            </span>
          </div>
          <p className="text-[12px] tracking-[0.08em] text-zinc-500 mt-2">
            Retune the entire environment with a single directive.
          </p>
        </div>
      </Reveal>

      <div className="jscroll flex-1 min-h-0 overflow-y-auto pr-1 pb-2">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
          {MODES.map((m, i) => (
            <ModeCard
              key={m.id}
              mode={m}
              i={i}
              big
              base={0.06}
              active={ctx.activeMode === m.id}
              onToggle={() => {
                const next = ctx.activeMode === m.id ? null : m.id;
                ctx.setActiveMode(next);
                ctx.pushToast(next ? `${m.name} ENGAGED` : "MODE DISENGAGED", next ? m.desc : "Returning to baseline systems");
                if (next) ctx.runAction("mode", m.name);
              }}
            />
          ))}
        </div>

        {active && (
          <Reveal i={5} className="glass-panel mt-5 p-5 flex items-center gap-4">
            <div className="grid place-items-center w-11 h-11 rounded-xl border border-accent-40 bg-accent-15 text-accent shadow-glow-sm shrink-0">
              <Power size={18} />
            </div>
            <div>
              <div className="text-[12px] font-semibold tracking-[0.22em] text-accent text-glow">{active.name} — LIVE TELEMETRY</div>
              <div className="text-[11px] text-zinc-500 mt-1 tracking-[0.05em]">
                All subsystems re-tuned. Press the mode again to revert to baseline operations.
              </div>
            </div>
            <div className="ml-auto flex items-end gap-[3px] h-8">
              {Array.from({ length: 14 }).map((_, i) => (
                <span
                  key={i}
                  className="w-1 rounded-sm bg-accent eq-bar"
                  style={{ animationDelay: `${i * 0.09}s`, boxShadow: "0 0 6px rgb(var(--accent) / 0.5)" }}
                />
              ))}
            </div>
          </Reveal>
        )}
      </div>
    </div>
  );
}
