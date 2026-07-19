import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Hexagon, Cpu, Globe } from "lucide-react";

import { APPS, APP_ICON_CHOICES, FOLDERS, MODES, SITES } from "./lib/data";
import type { AddKind, Ctx, ExtraItem, Flag, View } from "./lib/types";
import { naitroApi, onNaitroLog, type DashboardData } from "./lib/api";
import BootScreen from "./components/BootScreen";
import ParticleField from "./components/ParticleField";
import TopBar from "./components/TopBar";
import Sidebar from "./components/Sidebar";
import Toasts, { type Toast } from "./components/Toasts";
import AddItemModal from "./components/AddItemModal";
import Dashboard from "./views/Dashboard";
import AppsView from "./views/AppsView";
import FoldersView from "./views/FoldersView";
import WebsitesView from "./views/WebsitesView";
import ModesView from "./views/ModesView";
import SettingsView from "./views/SettingsView";

type Extras = Record<AddKind, ExtraItem[]>;
const EMPTY_EXTRAS: Extras = { apps: [], folders: [], sites: [] };

const loadExtras = (): Extras => {
  try {
    const raw = localStorage.getItem("naitro.extras");
    if (!raw) return EMPTY_EXTRAS;
    return { ...EMPTY_EXTRAS, ...(JSON.parse(raw) as Partial<Extras>) };
  } catch {
    return EMPTY_EXTRAS;
  }
};

const VIEWS: View[] = ["dashboard", "apps", "folders", "websites", "modes", "settings"];

export default function App() {
  const [booted, setBooted] = useState(false);
  const [view, setView] = useState<View>("dashboard");
  const [accent, setAccent] = useState("168 85 247");
  const [speed, setSpeed] = useState(1);
  const [flags, setFlags] = useState<Record<Flag, boolean>>({ particles: true, scanlines: true, parallax: true, voice: true });
  const [activeMode, setActiveMode] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [extras, setExtras] = useState<Extras>(loadExtras);
  const [addKind, setAddKind] = useState<AddKind | null>(null);
  const [minimized, setMinimized] = useState(false);
  const [maximized, setMaximized] = useState(true);
  const [serverData, setServerData] = useState<DashboardData | null>(null);
  const toastId = useRef(0);
  const spot = useRef<HTMLDivElement>(null);

  /* ---------- load real data from NaitroEngine on boot ---------- */
  useEffect(() => {
    naitroApi.getDashboardData().then((data) => {
      if (data) setServerData(data);
    });
  }, []);

  const [speechStatus, setSpeechStatus] = useState<{ who: string; text: string } | null>(null);
  const speechStatusTimer = useRef<number | null>(null);

  /* ---------- stream engine.log() to the center-orb status display ----------
     Conversational lines ("YOU: ..." / "NaiTRO: ...") show under the logo
     instead of as bottom toasts -- toasts were getting noisy/annoying during
     back-and-forth conversation. Non-conversational diagnostic lines (no
     "who: " prefix, e.g. TTS errors) still surface as a toast since those
     are one-off warnings worth calling out, not part of the conversation. */
  useEffect(() => {
    return onNaitroLog((line) => {
      const idx = line.indexOf(": ");
      if (idx === -1) {
        pushToast("NaiTRO", line);
        return;
      }
      const who = line.slice(0, idx);
      const text = line.slice(idx + 2);
      setSpeechStatus({ who: who === "YOU" ? "You" : who, text });
      if (speechStatusTimer.current) window.clearTimeout(speechStatusTimer.current);
      speechStatusTimer.current = window.setTimeout(() => setSpeechStatus(null), 8000);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------- live speaking/listening status ---------- */
  useEffect(() => {
    const iv = window.setInterval(async () => {
      const status = await naitroApi.getStatus();
      if (status) setFlags((f) => (f.voice === status.listening ? f : { ...f, voice: status.listening }));
    }, 800);
    return () => window.clearInterval(iv);
  }, []);

  /* ---------- effects ---------- */
  useEffect(() => { document.documentElement.style.setProperty("--accent", accent); }, [accent]);
  useEffect(() => { document.documentElement.style.setProperty("--speed", String(speed)); }, [speed]);
  useEffect(() => { try { localStorage.setItem("naitro.extras", JSON.stringify(extras)); } catch { /* noop */ } }, [extras]);

  /* ---------- toasts ---------- */
  const pushToast = useCallback((title: string, msg?: string) => {
    const id = ++toastId.current;
    setToasts((ts) => [...ts.slice(-2), { id, title, msg }]);
    window.setTimeout(() => setToasts((ts) => ts.filter((t) => t.id !== id)), 3380);
  }, []);

  /* ---------- derived data (real backend data when available, mock as fallback/preview) ---------- */
  const PALETTE = ["#a78bfa", "#f0abfc", "#67e8f9", "#6ee7b7", "#fcd34d", "#fda4af", "#93c5fd", "#e8e8ec"];
  const colorFor = (name: string, i: number) => PALETTE[i % PALETTE.length] ?? "#a78bfa";

  const apps = useMemo(() => {
    const base = serverData
      ? Object.keys(serverData.apps).map((name, i) => ({
          id: name.toLowerCase(), name, Icon: Cpu, color: colorFor(name, i),
        }))
      : APPS;
    return [
      ...base,
      ...extras.apps.map((e) => ({ id: e.id, name: e.name, Icon: APP_ICON_CHOICES[e.icon] ?? Cpu, color: e.color, custom: true })),
    ];
  }, [serverData, extras]);

  const folders = useMemo(() => {
    const base = serverData
      ? Object.keys(serverData.folders).map((name, i) => ({ id: name.toLowerCase(), name, color: colorFor(name, i) }))
      : FOLDERS;
    return [...base, ...extras.folders.map((e) => ({ id: e.id, name: e.name, color: e.color, custom: true }))];
  }, [serverData, extras]);

  const sites = useMemo(() => {
    const base = serverData
      ? Object.keys(serverData.websites).map((name, i) => ({
          id: name.toLowerCase(), name, Icon: Globe, color: colorFor(name, i), hex: true,
        }))
      : SITES;
    return [
      ...base,
      ...extras.sites.map((e) => ({ id: e.id, name: e.name, Icon: Globe, color: e.color, hex: true, custom: true })),
    ];
  }, [serverData, extras]);

  const addExtra = useCallback((kind: AddKind, item: ExtraItem) => {
    setExtras((p) => ({ ...p, [kind]: [...p[kind], item] }));
    pushToast("Shortcut created", item.name);
    // Persist to NaiTRO's real config too, not just local browser storage.
    const apiKind = kind === "sites" ? "website" : kind === "folders" ? "folder" : "app";
    naitroApi.addItem(apiKind, item.name, item.name);
  }, [pushToast]);

  const removeExtra = useCallback((kind: AddKind, id: string) => {
    setExtras((p) => ({ ...p, [kind]: p[kind].filter((x) => x.id !== id) }));
    pushToast("Shortcut removed", "Neural index rebalanced");
  }, [pushToast]);

  const runAction = useCallback((kind: "app" | "folder" | "website" | "mode", name: string) => {
    naitroApi.runAction(kind, name).then((res) => {
      if (res && !res.ok) pushToast("Couldn't complete that", res.message || name);
    });
  }, [pushToast]);

  const ctx: Ctx = {
    pushToast,
    setView,
    openAdd: (k) => setAddKind(k),
    removeExtra,
    runAction,
    parallax: flags.parallax,
    voice: flags.voice,
    setVoice: (v) => {
      setFlags((f) => ({ ...f, voice: v }));
      naitroApi.toggleVoice(v);
      pushToast(v ? "Voice input online" : "Voice input muted", v ? 'Say "Hey NaiTRO" anytime' : "Microphone suspended");
    },
    activeMode,
    setActiveMode,
    accent,
    setAccent,
    speed,
    setSpeed,
    flags,
    toggleFlag: (f) => setFlags((p) => ({ ...p, [f]: !p[f] })),
    apps,
    folders,
    sites,
    speechStatus,
  };

  /* ---------- keyboard shortcuts ---------- */
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!booted || addKind) return;
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT") return;
      const n = Number(e.key);
      if (n >= 1 && n <= 6) setView(VIEWS[n - 1]);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [booted, addKind]);

  /* ---------- spotlight ---------- */
  const onPointerMove = (e: React.PointerEvent) => {
    if (spot.current) spot.current.style.transform = `translate(${e.clientX - 320}px, ${e.clientY - 320}px)`;
  };

  const status = activeMode ? MODES.find((m) => m.id === activeMode)?.name ?? "SYSTEM ONLINE" : "SYSTEM ONLINE";

  return (
    <div className="h-screen w-screen overflow-hidden relative" onPointerMove={onPointerMove}>
      {/* layers */}
      <ParticleField rgb={accent} enabled={flags.particles && booted} />
      <div ref={spot} className="spotlight hidden md:block" />
      {flags.scanlines && (
        <div className="fixed inset-0 pointer-events-none z-40 overflow-hidden">
          <div className="absolute inset-0 scanlines opacity-70" />
          <div className="sweep" />
        </div>
      )}
      <div className="fixed inset-0 pointer-events-none noise z-40" />
      <div className="fixed inset-0 pointer-events-none vignette z-[45]" />

      {/* desktop shell */}
      {booted && (
        <motion.div
          layout
          animate={minimized ? { opacity: 0, scale: 0.82, y: 90, filter: "blur(10px)" } : { opacity: 1, scale: 1, y: 0, filter: "blur(0px)" }}
          transition={{ type: "spring", stiffness: 200, damping: 26 }}
          className={`relative z-10 h-full flex flex-col ${maximized ? "p-3 md:p-4 xl:p-5" : "p-6 md:p-12"} ${minimized ? "pointer-events-none" : ""}`}
        >
          <motion.div
            layout
            className={`relative flex-1 min-h-0 flex flex-col transition-shadow duration-500 ${
              maximized ? "" : "rounded-3xl border border-accent-15 bg-black/40 shadow-glow overflow-hidden px-4 pt-2 pb-3"
            }`}
          >
            <TopBar
              status={status}
              voice={flags.voice}
              setVoice={ctx.setVoice}
              maximized={maximized}
              onMinimize={() => setMinimized(true)}
              onMaximize={() => {
                setMaximized((m) => !m);
                pushToast(maximized ? "Window released" : "Fullscreen engaged", maximized ? "Floating viewport mode" : "Edge-to-edge rendering");
              }}
              onClose={() => naitroApi.close()}
              onOpenSettings={() => setView("settings")}
              onPingWifi={() => pushToast("Uplink stable", "980 Mb/s — quantum relay node 7")}
            />
            <div className="hairline-x mb-3" />

            <div className="flex flex-1 min-h-0 gap-4 xl:gap-5">
              <Sidebar view={view} setView={setView} voice={flags.voice} setVoice={ctx.setVoice} />
              <div className="hairline-y self-stretch shrink-0" />
              <main className="flex-1 min-w-0 min-h-0 relative">
                <div className="jscroll h-full overflow-y-auto overscroll-contain pr-1">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={view}
                      initial={{ opacity: 0, y: 18, filter: "blur(4px)" }}
                      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                      exit={{ opacity: 0, y: -14, filter: "blur(4px)", transition: { duration: 0.16 } }}
                      transition={{ duration: 0.3, ease: [0.25, 0.8, 0.25, 1] }}
                      className="h-full"
                    >
                      {view === "dashboard" && <Dashboard ctx={ctx} />}
                      {view === "apps" && <AppsView ctx={ctx} />}
                      {view === "folders" && <FoldersView ctx={ctx} />}
                      {view === "websites" && <WebsitesView ctx={ctx} />}
                      {view === "modes" && <ModesView ctx={ctx} />}
                      {view === "settings" && <SettingsView ctx={ctx} />}
                    </motion.div>
                  </AnimatePresence>
                </div>
              </main>
            </div>
          </motion.div>
        </motion.div>
      )}

      {/* restore pill when minimized */}
      <AnimatePresence>
        {minimized && (
          <motion.button
            initial={{ opacity: 0, y: 40, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 40, scale: 0.9 }}
            transition={{ type: "spring", stiffness: 300, damping: 24 }}
            onClick={() => setMinimized(false)}
            className="fixed bottom-7 left-1/2 -translate-x-1/2 z-[65] flex items-center gap-3 px-6 py-3 rounded-2xl glass-panel cursor-pointer hover:shadow-glow transition-shadow group"
          >
            <Hexagon size={16} className="text-accent sp drop-accent" style={{ ["--dur" as string]: "6s" }} />
            <span className="font-orbitron text-[11px] font-semibold tracking-[0.3em] text-white">NaiTRO</span>
            <span className="font-mono2 text-[9px] tracking-[0.26em] text-zinc-500 group-hover:text-accent transition-colors">
              TAP TO RESTORE
            </span>
            <span className="w-1.5 h-1.5 rounded-full bg-accent breathe shadow-glow-sm" />
          </motion.button>
        )}
      </AnimatePresence>

      <Toasts toasts={toasts} />
      <AddItemModal kind={addKind} onClose={() => setAddKind(null)} onSubmit={addExtra} />

      <AnimatePresence>
        {!booted && <BootScreen key="boot" onDone={() => setBooted(true)} />}
      </AnimatePresence>
    </div>
  );
}
