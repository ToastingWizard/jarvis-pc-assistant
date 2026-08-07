import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Cpu, Globe } from "lucide-react";

import { APPS, APP_ICON_CHOICES, FOLDERS, MODES, SITES } from "./lib/data";
import type { AddKind, Ctx, ExtraItem, Flag, View } from "./lib/types";
import { naitroApi, onNaitroLog, type DashboardData, type ModeInfo } from "./lib/api";
import BootScreen from "./components/BootScreen";
import ParticleField from "./components/ParticleField";
import TopBar from "./components/TopBar";
import Sidebar from "./components/Sidebar";
import Toasts, { type Toast } from "./components/Toasts";
import AddItemModal from "./components/AddItemModal";
import ModeBuilderModal from "./components/ModeBuilderModal";
import Dashboard from "./views/Dashboard";
import AppsView from "./views/AppsView";
import FoldersView from "./views/FoldersView";
import WebsitesView from "./views/WebsitesView";
import ModesView from "./views/ModesView";
import SettingsView from "./views/SettingsView";
import BrowserView from "./views/BrowserView";

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

const VIEWS: View[] = ["dashboard", "apps", "folders", "websites", "modes", "browser", "settings"];

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
  // Mode builder: undefined = closed, null = new mode, ModeInfo = editing.
  const [builderMode, setBuilderMode] = useState<ModeInfo | null | undefined>(undefined);
  const [maximized, setMaximized] = useState(true);
  const [serverData, setServerData] = useState<DashboardData | null>(null);
  const toastId = useRef(0);
  const spot = useRef<HTMLDivElement>(null);

  /* ---------- load real data from NaitroEngine on boot ---------- */
  useEffect(() => {
    const load = () => {
      naitroApi.getDashboardData().then((data) => {
        if (data) {
          setServerData(data);
          // Fresh installs ship with no AI key. Surface the one-time hint
          // that leads the user to Settings → Neural Uplink — the only
          // way the voice assistant / smart replies come online.
          if (data.ai_status && !data.ai_status.has_nvidia && !data.ai_status.has_gemini) {
            pushToast("No AI key set", "Open Settings → Neural Uplink to enable the assistant");
          }
        }
      });
    };
    // pywebview injects window.pywebview asynchronously.  If the API
    // isn't ready yet, wait for the pywebviewready event; otherwise
    // fetch immediately.
    if (typeof window !== "undefined" && !window.pywebview?.api) {
      const handler = () => { load(); };
      window.addEventListener("pywebviewready", handler, { once: true });
      return () => window.removeEventListener("pywebviewready", handler);
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------- sync active mode from the backend (engine persists it) ---------- */
  useEffect(() => {
    if (serverData) setActiveMode(serverData.active_mode ?? null);
  }, [serverData]);

  const [speechStatus, setSpeechStatus] = useState<{ who: string; text: string } | null>(null);
  const speechStatusTimer = useRef<number | null>(null);
  const lastVoiceError = useRef<string | null>(null);

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
      if (status) {
        setFlags((f) => (f.voice === status.listening ? f : { ...f, voice: status.listening }));
        // Toast once per mic failure (not every 800 ms poll) so a demo
        // with an unplugged mic shows what's wrong instead of silently
        // going mute.
        if (status.voice_error && lastVoiceError.current !== status.voice_error) {
          lastVoiceError.current = status.voice_error;
          pushToast("Microphone offline", "Plug in a mic — NaiTRO is retrying");
        } else if (!status.voice_error) {
          lastVoiceError.current = null;
        }
      }
    }, 800);
    return () => window.clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  const colorFor = (_name: string, i: number) => PALETTE[i % PALETTE.length] ?? "#a78bfa";

  const apps = useMemo(() => {
    const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
    const base = serverData
      ? Object.keys(serverData.apps).map((name, i) => {
          const meta = serverData.apps[name];
          return {
            id: name.toLowerCase(),
            name,
            Icon: Cpu,
            color: colorFor(name, i),
            img: meta?.icon || undefined,
          };
        })
      : APPS;
    // Filter localStorage extras that already exist in server data to
    // avoid duplicate entries — the server versions carry real icons,
    // the extras versions don't.  Use substring matching so "Minecraft"
    // in extras is filtered when the server has "Minecraft Launcher".
    const baseNorms = base.map((a) => norm(a.name));
    return [
      ...base,
      ...extras.apps
        .filter((e) => {
          const en = norm(e.name);
          return !baseNorms.some((bn) => bn === en || bn.includes(en) || en.includes(bn));
        })
        .map((e) => ({ id: e.id, name: e.name, Icon: APP_ICON_CHOICES[e.icon] ?? Cpu, color: e.color, custom: true })),
    ];
  }, [serverData, extras]);

  const folders = useMemo(() => {
    const base = serverData
      ? Object.keys(serverData.folders).map((name, i) => ({ id: name.toLowerCase(), name, color: colorFor(name, i) }))
      : FOLDERS;
    const baseNames = new Set(base.map((f) => f.name.toLowerCase()));
    return [
      ...base,
      ...extras.folders
        .filter((e) => !baseNames.has(e.name.toLowerCase()))
        .map((e) => ({ id: e.id, name: e.name, color: e.color, custom: true })),
    ];
  }, [serverData, extras]);

  const sites = useMemo(() => {
    const base = serverData
      ? Object.keys(serverData.websites).map((name, i) => ({
          id: name.toLowerCase(), name, Icon: Globe, color: colorFor(name, i), hex: true,
        }))
      : SITES;
    const baseNames = new Set(base.map((s) => s.name.toLowerCase()));
    return [
      ...base,
      ...extras.sites
        .filter((e) => !baseNames.has(e.name.toLowerCase()))
        .map((e) => ({ id: e.id, name: e.name, Icon: Globe, color: e.color, hex: true, custom: true })),
    ];
  }, [serverData, extras]);

  const modes = useMemo(() => {
    if (!serverData) return MODES.map((m) => ({ name: m.name, desc: m.desc, steps: [], style: "" }));
    return Object.values(serverData.modes);
  }, [serverData]);

  const addExtra = useCallback(async (kind: AddKind, item: ExtraItem) => {
    setExtras((p) => ({ ...p, [kind]: [...p[kind], item] }));
    // Persist to NaiTRO's real config too, not just local browser storage.
    const apiKind = kind === "sites" ? "website" : kind === "folders" ? "folder" : "app";
    const result = await naitroApi.addItem(apiKind, item.name, item.name);
    // Re-fetch dashboard data so the newly added app appears with its
    // extracted icon (not just the user-chosen glyph from extras).
    // This also deduplicates: once the server has the app, the extras
    // entry is automatically filtered out by the baseNames check below.
    const data = await naitroApi.getDashboardData();
    if (data) setServerData(data);
    // Show the backend's resolution message — includes whether the app
    // was found and which target it resolved to, or a helpful hint if
    // the name can't be found.
    if (result && result.message) {
      pushToast(
        result.ok ? "Shortcut created" : "Could not find that app",
        result.message,
      );
    } else {
      pushToast("Shortcut created", item.name);
    }
  }, [pushToast]);

  const removeItem = useCallback(async (kind: "app" | "folder" | "website", name: string, id?: string) => {
    // Drop any matching localStorage extra first — the dashboards dedupe on
    // name, so the shortcut vanishes immediately even before the re-fetch.
    const addKind: AddKind = kind === "website" ? "sites" : kind === "folder" ? "folders" : "apps";
    setExtras((p) => ({
      ...p,
      [addKind]: p[addKind].filter((x) => x.name !== name && x.id !== id),
    }));
    // Permanent delete in the real config (also recorded in config["removed"]
    // so deep_merge_defaults can't resurrect it on the next launch).
    const result = await naitroApi.removeItem(kind, name);
    const data = await naitroApi.getDashboardData();
    if (data) setServerData(data);
    pushToast(result && result.ok ? "Shortcut deleted" : "Shortcut removed", name);
  }, [pushToast]);

  const deleteMode = useCallback(async (name: string) => {
    await naitroApi.deleteMode(name);
    const data = await naitroApi.getDashboardData();
    if (data) setServerData(data); // also clears active_mode if it was live
    pushToast("Mode deleted", name);
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
    removeItem,
    deleteMode,
    openModeBuilder: (mode) => setBuilderMode(mode ?? null),
    modes,
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
      if (n >= 1 && n <= 7) setView(VIEWS[n - 1]);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [booted, addKind]);

  /* ---------- spotlight ---------- */
  const onPointerMove = (e: React.PointerEvent) => {
    if (spot.current) spot.current.style.transform = `translate(${e.clientX - 320}px, ${e.clientY - 320}px)`;
  };

  const activeModeInfo = activeMode ? modes.find((m) => m.name === activeMode) : undefined;
  const status = activeModeInfo ? activeModeInfo.name.toUpperCase() : "SYSTEM ONLINE";

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
        <div className={`relative z-10 h-full flex flex-col ${maximized ? "p-3 md:p-4 xl:p-5" : "p-6 md:p-12"}`}>
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
              onMinimize={() => naitroApi.minimize()}
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
                      {view === "browser" && <BrowserView ctx={ctx} />}
                      {view === "settings" && <SettingsView ctx={ctx} />}
                    </motion.div>
                  </AnimatePresence>
                </div>
              </main>
            </div>
          </motion.div>
        </div>
      )}

      <Toasts toasts={toasts} />
      <AddItemModal kind={addKind} onClose={() => setAddKind(null)} onSubmit={addExtra} />
      <ModeBuilderModal
        mode={builderMode}
        onClose={() => setBuilderMode(undefined)}
        onSaved={(res, name) => {
          if (res && res.ok) {
            setBuilderMode(undefined);
            pushToast("Mode saved", name);
            naitroApi.getDashboardData().then((data) => { if (data) setServerData(data); });
          } else {
            pushToast("Couldn't save mode", res?.message || name);
          }
        }}
        picker={serverData?.picker ?? { apps: [], websites: [], folders: [], playlists: [] }}
      />

      <AnimatePresence>
        {!booted && <BootScreen key="boot" onDone={() => setBooted(true)} />}
      </AnimatePresence>
    </div>
  );
}
