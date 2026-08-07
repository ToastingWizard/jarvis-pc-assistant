import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Settings, Palette, Gauge, SlidersHorizontal, Cpu, KeyRound, Save, Check } from "lucide-react";
import { ACCENTS } from "../lib/data";
import { naitroApi, type AiStatus } from "../lib/api";
import type { Ctx } from "../lib/types";
import type { Flag } from "../lib/types";
import Reveal from "../components/Reveal";
import Panel from "../components/Panel";

function Switch({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`relative w-11 h-6 rounded-full transition-colors duration-300 cursor-pointer border ${
        on ? "bg-accent-20 border-accent-40 shadow-glow-sm" : "bg-white/5 border-white/10"
      }`}
    >
      <motion.span
        layout
        transition={{ type: "spring", stiffness: 600, damping: 32 }}
        className={`absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full ${
          on ? "left-[22px] bg-accent shadow-glow-sm" : "left-1 bg-zinc-500"
        }`}
      />
    </button>
  );
}

const FLAG_ROWS: { id: Flag; label: string; desc: string }[] = [
  { id: "particles", label: "PARTICLE FIELD", desc: "Ambient neural dust with cursor repulsion" },
  { id: "scanlines", label: "CRT SCANLINES",  desc: "Retro phosphor sweep across the viewport" },
  { id: "parallax",  label: "CORE PARALLAX",  desc: "Arc reactor tracks your cursor in 3D" },
  { id: "voice",     label: "VOICE FEEDBACK", desc: "Live microphone waveform in the sidebar" },
];

export default function SettingsView({ ctx }: { ctx: Ctx }) {
  const [up, setUp] = useState(0);
  const [load, setLoad] = useState(62);
  useEffect(() => {
    const iv = window.setInterval(() => setUp((u) => u + 1), 1000);
    const iv2 = window.setInterval(() => setLoad(58 + Math.round(Math.random() * 34)), 1600);
    return () => { window.clearInterval(iv); window.clearInterval(iv2); };
  }, []);

  const hh = String(Math.floor(up / 3600)).padStart(2, "0");
  const mm = String(Math.floor((up % 3600) / 60)).padStart(2, "0");
  const ss = String(up % 60).padStart(2, "0");
  const pct = Math.round(((ctx.speed - 0.4) / 1.8) * 100);

  /* ---- Neural Uplink: bring-your-own API key ---- */
  // The backend only ever reports booleans (has_nvidia / has_gemini),
  // never the key itself, so the inputs start empty and show a LINKED/
  // NO KEY badge for the actual state.
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [nvidiaKey, setNvidiaKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");

  const refreshAiStatus = useCallback(() => {
    naitroApi.getDashboardData().then((d) => {
      if (d?.ai_status) setAiStatus(d.ai_status);
    });
  }, []);

  useEffect(() => { refreshAiStatus(); }, [refreshAiStatus]);

  const saveKey = useCallback(async (provider: "nvidia" | "gemini", key: string, label: string) => {
    const res = await naitroApi.saveAiConfig(provider, key);
    if (provider === "nvidia") setNvidiaKey("");
    else setGeminiKey("");
    refreshAiStatus();
    ctx.pushToast(res?.ok ? label + " key saved" : "Couldn't save key", res?.message || "");
  }, [refreshAiStatus, ctx]);

  const AI_ROWS = [
    {
      provider: "nvidia" as const,
      label: "NVIDIA NIM",
      hint: "Primary brain — free key at build.nvidia.com",
      placeholder: "nvapi-...",
      value: nvidiaKey,
      set: setNvidiaKey,
      linked: aiStatus?.has_nvidia ?? false,
    },
    {
      provider: "gemini" as const,
      label: "GEMINI",
      hint: "Fallback — key at aistudio.google.com",
      placeholder: "AIza...",
      value: geminiKey,
      set: setGeminiKey,
      linked: aiStatus?.has_gemini ?? false,
    },
  ];

  return (
    <div className="flex flex-col h-full min-h-0">
      <Reveal i={0} className="mb-6 shrink-0">
        <div className="flex items-center gap-3">
          <Settings size={18} className="text-accent drop-accent sp" style={{ ["--dur" as string]: "14s" }} />
          <h1 className="font-orbitron text-xl font-bold tracking-[0.3em] grad-text">CONTROL DECK</h1>
        </div>
        <p className="text-[12px] tracking-[0.08em] text-zinc-500 mt-2">Every dial is live — changes apply instantly across the OS.</p>
      </Reveal>

      <div className="jscroll flex-1 min-h-0 overflow-y-auto pr-1 pb-2">
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 pt-1">
          {/* accent theme */}
          <Panel title="ACCENT MATRIX" Icon={Palette} i={1}>
            <div className="flex flex-wrap items-center gap-3.5">
              {ACCENTS.map((a) => {
                const on = ctx.accent === a.rgb;
                return (
                  <button
                    key={a.rgb}
                    onClick={() => { ctx.setAccent(a.rgb); ctx.pushToast("Accent re-mapped", a.name); }}
                    className="group flex flex-col items-center gap-2.5 cursor-pointer"
                  >
                    <motion.span
                      whileHover={{ scale: 1.15 }}
                      whileTap={{ scale: 0.9 }}
                      className="relative grid place-items-center w-11 h-11 rounded-xl border transition-all duration-200"
                      style={{
                        background: `rgb(${a.rgb} / 0.15)`,
                        borderColor: `rgb(${a.rgb} / ${on ? 0.9 : 0.3})`,
                        boxShadow: on ? `0 0 18px rgb(${a.rgb} / 0.55)` : "none",
                      }}
                    >
                      <span className="w-4 h-4 rounded-full" style={{ background: `rgb(${a.rgb})`, boxShadow: `0 0 10px rgb(${a.rgb})` }} />
                      {on && <Check size={11} className="absolute -top-1.5 -right-1.5 text-white bg-zinc-900 rounded-full p-[1px]" />}
                    </motion.span>
                    <span className={`font-mono2 text-[7px] tracking-[0.2em] ${on ? "text-white" : "text-zinc-600"}`}>{a.name}</span>
                  </button>
                );
              })}
            </div>
          </Panel>

          {/* animation speed */}
          <Panel title="TEMPORAL DIAL" Icon={Gauge} i={2}>
            <div className="flex items-center gap-5">
              <input
                type="range"
                min={0.4}
                max={2.2}
                step={0.05}
                value={ctx.speed}
                onChange={(e) => ctx.setSpeed(Number(e.target.value))}
                className="jr flex-1"
                style={{ ["--fill" as string]: `${pct}%` }}
              />
              <span className="font-orbitron text-lg font-bold text-accent text-glow w-20 text-right">
                {ctx.speed.toFixed(2)}x
              </span>
            </div>
            <div className="flex justify-between font-mono2 text-[8px] tracking-[0.28em] text-zinc-600 mt-2">
              <span>SLOW-MO</span><span>REALTIME</span><span>OVERDRIVE</span>
            </div>
            <div className="flex items-end gap-[3px] h-7 mt-5">
              {Array.from({ length: 30 }).map((_, i) => (
                <span
                  key={i}
                  className="flex-1 rounded-sm bg-accent/60 eq-bar"
                  style={{ animationDelay: `${i * 0.07}s`, animationDuration: `calc(${(1.4 - ctx.speed * 0.4).toFixed(2)}s / var(--speed))` }}
                />
              ))}
            </div>
          </Panel>

          {/* toggles */}
          <Panel title="SUBSYSTEMS" Icon={SlidersHorizontal} i={3}>
            <div className="flex flex-col divide-y divide-white/5">
              {FLAG_ROWS.map((f) => (
                <div key={f.id} className="flex items-center gap-4 py-3.5 first:pt-0 last:pb-0">
                  <div className="flex-1 min-w-0">
                    <div className="text-[12px] font-semibold tracking-[0.2em] text-zinc-100">{f.label}</div>
                    <div className="text-[10px] tracking-[0.06em] text-zinc-500 mt-0.5">{f.desc}</div>
                  </div>
                  <span className={`font-mono2 text-[8px] tracking-[0.3em] ${ctx.flags[f.id] ? "text-accent" : "text-zinc-600"}`}>
                    {ctx.flags[f.id] ? "ON" : "OFF"}
                  </span>
                  <Switch on={ctx.flags[f.id]} onClick={() => ctx.toggleFlag(f.id)} />
                </div>
              ))}
            </div>
          </Panel>

          {/* system info */}
          <Panel title="SYSTEM TELEMETRY" Icon={Cpu} i={4}>
            <div className="grid grid-cols-3 gap-3 mb-5">
              {[
                { k: "VERSION", v: "2.0.1" },
                { k: "UPTIME", v: `${hh}:${mm}:${ss}` },
                { k: "CORES", v: "12 / 12" },
              ].map((s) => (
                <div key={s.k} className="rounded-xl border border-white/[0.07] bg-black/25 p-3 text-center">
                  <div className="font-orbitron text-[13px] font-semibold text-white">{s.v}</div>
                  <div className="font-mono2 text-[7px] tracking-[0.3em] text-zinc-600 mt-1.5">{s.k}</div>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between font-mono2 text-[9px] tracking-[0.28em] text-zinc-500 mb-2">
              <span>NEURAL LOAD</span>
              <span className="text-accent">{load}%</span>
            </div>
            <div className="h-2 rounded-full bg-white/5 overflow-hidden">
              <motion.div
                animate={{ width: `${load}%` }}
                transition={{ type: "spring", stiffness: 90, damping: 20 }}
                className="h-full rounded-full bg-accent shadow-glow-sm"
              />
            </div>
            <div className="flex items-center gap-2 mt-5">
              <span className="w-1.5 h-1.5 rounded-full bg-accent breathe shadow-glow-sm" />
              <span className="font-mono2 text-[9px] tracking-[0.3em] text-zinc-500">ALL SYSTEMS NOMINAL</span>
            </div>
          </Panel>

          {/* AI API keys — users bring their own key; NaiTRO ships with none */}
          <Panel title="NEURAL UPLINK" Icon={KeyRound} i={5}>
            <div className="flex flex-col divide-y divide-white/5">
              {AI_ROWS.map((row) => (
                <div key={row.provider} className="py-3.5 first:pt-0 last:pb-0">
                  <div className="flex items-center justify-between gap-4 mb-2">
                    <div>
                      <div className="text-[12px] font-semibold tracking-[0.2em] text-zinc-100">{row.label}</div>
                      <div className="text-[10px] tracking-[0.06em] text-zinc-500 mt-0.5">{row.hint}</div>
                    </div>
                    <span className={`font-mono2 text-[8px] tracking-[0.3em] ${row.linked ? "text-accent" : "text-zinc-600"}`}>
                      {row.linked ? "LINKED" : "NO KEY"}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={row.value}
                      onChange={(e) => row.set(e.target.value)}
                      placeholder={row.placeholder}
                      autoComplete="off"
                      spellCheck={false}
                      className="jtext flex-1 px-3 py-2 text-[12px] tracking-[0.08em]"
                    />
                    <button
                      onClick={() => saveKey(row.provider, row.value, row.label)}
                      disabled={!row.value.trim()}
                      className="flex items-center gap-1 px-3 py-2 rounded-lg bg-accent-15 border border-accent-40 text-accent text-[10px] font-semibold tracking-[0.2em] hover:shadow-glow transition-shadow disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer shrink-0"
                    >
                      <Save size={12} /> {row.linked ? "UPDATE" : "SAVE"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <p className="font-mono2 text-[8px] tracking-[0.2em] text-zinc-600 mt-3 leading-relaxed">
              YOUR KEY NEVER LEAVES THIS MACHINE — IT'S STORED IN CONFIG.JSON. NaiTRO SHIPS WITH NO KEY;
              THE ASSISTANT WAKES UP THE MOMENT ONE IS LINKED.
            </p>
          </Panel>
        </div>
      </div>
    </div>
  );
}
