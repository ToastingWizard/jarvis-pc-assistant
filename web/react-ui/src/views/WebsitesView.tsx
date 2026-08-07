import { Globe, Plus, ArrowUpRight } from "lucide-react";
import type { Ctx } from "../lib/types";
import Reveal from "../components/Reveal";
import Tilt from "../components/Tilt";

const URLS: Record<string, string> = {
  google: "google.com", youtube: "youtube.com", github: "github.com",
  gmail: "mail.google.com", drive: "drive.google.com", wikipedia: "wikipedia.org",
};

export default function WebsitesView({ ctx }: { ctx: Ctx }) {
  return (
    <div className="flex flex-col h-full min-h-0">
      <Reveal i={0} className="flex items-center justify-between gap-4 mb-5 shrink-0">
        <div>
          <div className="flex items-center gap-3">
            <Globe size={18} className="text-accent drop-accent" />
            <h1 className="font-orbitron text-xl font-bold tracking-[0.3em] grad-text">WEB UPLINKS</h1>
            <span className="font-mono2 text-[9px] tracking-[0.24em] px-2 py-1 rounded-md border border-accent-25 bg-accent-10 text-accent">
              {ctx.sites.length} ROUTES
            </span>
          </div>
          <p className="text-[12px] tracking-[0.08em] text-zinc-500 mt-2">One tap and the uplink tunnels you straight there.</p>
        </div>
        <button
          onClick={() => ctx.openAdd("sites")}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-accent-15 border border-accent-40 text-accent text-[10px] font-semibold tracking-[0.26em] hover:shadow-glow transition-shadow cursor-pointer"
        >
          <Plus size={13} /> NEW
        </button>
      </Reveal>

      <div className="jscroll flex-1 min-h-0 overflow-y-auto pr-1 pb-2">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 pt-2">
          {ctx.sites.map((s, i) => (
            <Reveal key={s.id} i={i} base={0.05}>
              <Tilt
                max={9}
                scale={1.03}
                onClick={() => { ctx.pushToast("Opening " + s.name, `Tunneling to ${URLS[s.id] ?? "shortcut"}…`); ctx.runAction("website", s.name); }}
                className="relative glass-panel !rounded-2xl p-5 cursor-pointer overflow-hidden group"
              >
                <div
                  className="absolute -right-8 -top-8 w-28 h-28 rounded-full blur-2xl opacity-0 group-hover:opacity-50 transition-opacity duration-500"
                  style={{ background: `${s.color}55` }}
                />
                <div className="flex items-center gap-4">
                  <div
                    className="grid place-items-center w-14 h-14 rounded-2xl border transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-3 shrink-0"
                    style={{ borderColor: `${s.color}44`, background: `${s.color}0f`, color: s.color }}
                  >
                    {s.hex ? (
                      <span className="font-orbitron font-bold text-xl" style={{ textShadow: `0 0 14px ${s.color}` }}>
                        {s.name.charAt(0).toUpperCase()}
                      </span>
                    ) : (
                      <s.Icon size={28} />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[14px] font-semibold tracking-[0.1em] text-white">{s.name}</span>
                      <ArrowUpRight size={13} className="text-zinc-600 group-hover:text-accent transition-all duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                    </div>
                    <div className="font-mono2 text-[9px] tracking-[0.2em] text-zinc-500 mt-1.5 uppercase">
                      {URLS[s.id] ?? "custom route"}
                    </div>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); ctx.removeItem("website", s.name, s.id); }}
                    className="absolute top-2 right-2 font-mono2 text-[9px] text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                  >
                    ✕
                  </button>
                </div>
                <div className="hairline-x mt-4 opacity-40 group-hover:opacity-100 transition-opacity" />
                <div className="flex items-center justify-between mt-3">
                  <span className="font-mono2 text-[8px] tracking-[0.3em] text-zinc-600">LATENCY 4MS</span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full breathe" style={{ background: s.color, boxShadow: `0 0 8px ${s.color}` }} />
                    <span className="font-mono2 text-[8px] tracking-[0.3em]" style={{ color: s.color }}>SECURE</span>
                  </span>
                </div>
              </Tilt>
            </Reveal>
          ))}
        </div>
      </div>
    </div>
  );
}
