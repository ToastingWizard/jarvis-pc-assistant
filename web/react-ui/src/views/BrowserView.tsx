import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Monitor, MonitorOff, Globe, Send, Link,
} from "lucide-react";
import type { Ctx } from "../lib/types";
import { naitroApi, type BrowserStatus, type BrowserTab } from "../lib/api";
import Reveal from "../components/Reveal";

type AgentMessage = { role: "user" | "system"; text: string };

export default function BrowserView({ ctx }: { ctx: Ctx }) {
  const [status, setStatus] = useState<BrowserStatus | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEnd = useRef<HTMLDivElement>(null);

  const refreshStatus = useCallback(async () => {
    const s = await naitroApi.browserStatus();
    if (s) setStatus(s);
  }, []);

  useEffect(() => { refreshStatus(); }, [refreshStatus]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const addMsg = (role: "user" | "system", text: string) =>
    setMessages((prev) => [...prev.slice(-40), { role, text }]);

  const handleStart = async () => {
    setLoading(true);
    const r = await naitroApi.browserStart();
    if (r) addMsg("system", r.ok ? r.message : r.message || "Failed to start browser");
    await refreshStatus();
    setLoading(false);
  };

  const handleStop = async () => {
    setLoading(true);
    const r = await naitroApi.browserStop();
    if (r) addMsg("system", r.message || "Browser stopped");
    await refreshStatus();
    setLoading(false);
  };

  const handleCommand = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    addMsg("user", text);
    setLoading(true);
    const result = await naitroApi.browserCommand(text);
    if (result) {
      addMsg("system", result.message || (result.ok ? "Done" : "Failed"));
      if (result.confirmation_required) {
        addMsg("system", "Say 'yes' to confirm or 'no' to cancel.");
      }
      if (!result.ok) ctx.pushToast("Browser", result.message);
    }
    await refreshStatus();
    setLoading(false);
  };

  const tabs: BrowserTab[] = status?.tabs ?? [];
  const snap = status?.current_snapshot;
  const running = status?.running ?? false;

  return (
    <div className="flex flex-col h-full min-h-0 gap-4">
      {/* Header + status */}
      <Reveal i={0} className="flex items-center justify-between gap-4 shrink-0">
        <div>
          <div className="flex items-center gap-2 font-mono2 text-[10px] tracking-[0.26em] text-zinc-500">
            <span className="text-accent">ROOT</span>
            <span className="text-zinc-700">/</span>
            <span className="text-accent text-glow">BROWSER</span>
          </div>
          <h2 className="text-[13px] font-semibold tracking-[0.2em] text-zinc-100 mt-1">
            BROWSER AGENT
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${running ? "bg-emerald-400 shadow-glow-sm" : "bg-zinc-600"}`}
          />
          <span className="font-mono2 text-[9px] tracking-[0.2em] text-zinc-500">
            {running ? "ONLINE" : "OFFLINE"}
          </span>
        </div>
      </Reveal>

      <div className="hairline-x" />

      {/* Start / Stop + tabs summary */}
      <Reveal i={1} className="flex items-center gap-3 shrink-0">
        {!running ? (
          <button
            onClick={handleStart}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-[11px] font-semibold tracking-[0.2em] bg-accent/10 border border-accent/25 text-accent hover:bg-accent/20 transition-colors cursor-pointer disabled:opacity-40"
          >
            <Monitor size={14} />
            START
          </button>
        ) : (
          <button
            onClick={handleStop}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-[11px] font-semibold tracking-[0.2em] bg-red-500/10 border border-red-500/25 text-red-400 hover:bg-red-500/20 transition-colors cursor-pointer disabled:opacity-40"
          >
            <MonitorOff size={14} />
            STOP
          </button>
        )}
        {tabs.length > 0 && (
          <span className="font-mono2 text-[9px] tracking-[0.2em] text-zinc-500">
            {tabs.length} tab{tabs.length !== 1 ? "s" : ""} open
          </span>
        )}
      </Reveal>

      {/* Tab list */}
      {tabs.length > 0 && (
        <Reveal i={2} className="flex gap-2 overflow-x-auto shrink-0 pb-1">
          {tabs.map((t) => (
            <div
              key={t.tab_id}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[10px] font-mono2 tracking-wider shrink-0 ${
                t.is_active
                  ? "border-accent/30 bg-accent/10 text-accent"
                  : "border-white/5 bg-white/3 text-zinc-500"
              }`}
            >
              <Globe size={11} className="shrink-0" />
              <span className="truncate max-w-[140px]">{t.title || t.url || "untitled"}</span>
            </div>
          ))}
        </Reveal>
      )}

      {/* Page snapshot */}
      {snap && (
        <Reveal i={3} className="glass-panel rounded-xl p-4 shrink-0">
          <div className="flex items-center gap-2 mb-2">
            <Link size={11} className="text-accent shrink-0" />
            <span className="font-mono2 text-[9px] tracking-[0.2em] text-accent/80 truncate">
              {snap.url}
            </span>
          </div>
          <div className="text-[11px] font-semibold text-zinc-200 mb-1 truncate">{snap.title}</div>
          <div className="text-[10px] text-zinc-500 leading-relaxed line-clamp-3">
            {snap.visible_text.slice(0, 500)}{snap.visible_text.length > 500 ? "..." : ""}
          </div>
          {snap.links.length > 0 && (
            <div className="mt-2 flex gap-1.5 flex-wrap">
              {snap.links.slice(0, 8).map((l, i) => (
                <span
                  key={i}
                  className="inline-block px-2 py-0.5 rounded bg-white/5 border border-white/5 text-[9px] text-zinc-500 font-mono2 truncate max-w-[120px]"
                >
                  {l.text || l.href}
                </span>
              ))}
            </div>
          )}
        </Reveal>
      )}

      {/* Command input */}
      <Reveal i={4} className="shrink-0">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCommand()}
            placeholder={running ? "Type a browser command..." : "Start the browser first"}
            disabled={!running || loading}
            className="flex-1 px-4 py-2.5 rounded-xl bg-white/5 border border-white/8 text-[11px] font-mono2 tracking-wider text-zinc-200 placeholder:text-zinc-600 focus:border-accent/30 focus:outline-none transition-colors disabled:opacity-40"
          />
          <button
            onClick={handleCommand}
            disabled={!running || loading || !input.trim()}
            className="px-4 py-2.5 rounded-xl bg-accent/10 border border-accent/25 text-accent hover:bg-accent/20 transition-colors cursor-pointer disabled:opacity-30"
          >
            <Send size={14} />
          </button>
        </div>
      </Reveal>

      {/* Message log */}
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain glass-panel rounded-xl p-3">
        {messages.length === 0 && (
          <div className="text-[10px] font-mono2 text-zinc-600 tracking-wider">
            {running
              ? "Enter a command like 'open https://example.com', 'click Submit', or 'read page'."
              : "Start the browser to begin."}
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <AnimatePresence initial={false}>
            {messages.map((m, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.15 }}
                className={`text-[10px] font-mono2 tracking-wider leading-relaxed ${
                  m.role === "user" ? "text-accent/80" : "text-zinc-500"
                }`}
              >
                <span className="text-zinc-700 mr-1">
                  {m.role === "user" ? ">" : "*"}
                </span>
                {m.text}
              </motion.div>
            ))}
          </AnimatePresence>
          <div ref={messagesEnd} />
        </div>
      </div>
    </div>
  );
}
