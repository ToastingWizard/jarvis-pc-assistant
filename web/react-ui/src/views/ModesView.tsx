import { Zap, Power, Plus } from "lucide-react";
import type { Ctx } from "../lib/types";
import type { ModeInfo } from "../lib/api";
import { naitroApi } from "../lib/api";
import ModeCard from "../components/ModeCard";
import Reveal from "../components/Reveal";

export default function ModesView({ ctx }: { ctx: Ctx }) {
  const active = ctx.modes.find((m) => m.name === ctx.activeMode) ?? null;

  const toggle = (m: ModeInfo) => {
    if (ctx.activeMode === m.name) {
      ctx.setActiveMode(null);
      ctx.pushToast("MODE DISENGAGED", "Returning to baseline systems");
      naitroApi.deactivateMode();
    } else {
      ctx.setActiveMode(m.name);
      ctx.pushToast(`${m.name.toUpperCase()} ENGAGED`, m.desc);
      ctx.runAction("mode", m.name);
    }
  };

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
              {active ? active.name.toUpperCase() : "BASELINE"}
            </span>
          </div>
          <p className="text-[12px] tracking-[0.08em] text-zinc-500 mt-2">
            Retune the entire environment with a single directive.
          </p>
        </div>
        <button
          onClick={() => ctx.openModeBuilder()}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-accent-15 border border-accent-40 text-accent text-[10px] font-semibold tracking-[0.26em] hover:shadow-glow transition-shadow cursor-pointer shrink-0"
        >
          <Plus size={13} /> NEW MODE
        </button>
      </Reveal>

      <div className="jscroll flex-1 min-h-0 overflow-y-auto pr-1 pb-2">
        {ctx.modes.length === 0 ? (
          <div className="h-full grid place-items-center">
            <div className="text-center">
              <div className="font-orbitron text-zinc-600 tracking-[0.3em] text-sm">NO MODES CONFIGURED</div>
              <div className="font-mono2 text-[10px] tracking-[0.2em] text-zinc-700 mt-2">FORGE YOUR FIRST ROUTINE OR PERSONALITY</div>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
            {ctx.modes.map((m, i) => (
              <ModeCard
                key={m.name}
                mode={m}
                i={i}
                big
                base={0.06}
                active={ctx.activeMode === m.name}
                onToggle={() => toggle(m)}
                onDelete={() => ctx.deleteMode(m.name)}
              />
            ))}
          </div>
        )}

        {active && (
          <Reveal i={5} className="glass-panel mt-5 p-5 flex items-center gap-4">
            <div className="grid place-items-center w-11 h-11 rounded-xl border border-accent-40 bg-accent-15 text-accent shadow-glow-sm shrink-0">
              <Power size={18} />
            </div>
            <div>
              <div className="text-[12px] font-semibold tracking-[0.22em] text-accent text-glow">{active.name.toUpperCase()} — LIVE TELEMETRY</div>
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
