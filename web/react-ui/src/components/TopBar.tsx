import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Hexagon, Mic, MicOff, Settings, Wifi, Volume2, Minus, Square, X, BatteryMedium } from "lucide-react";

const pad = (n: number) => String(n).padStart(2, "0");

interface Props {
  status: string;
  voice: boolean;
  setVoice: (v: boolean) => void;
  maximized: boolean;
  onMinimize: () => void;
  onMaximize: () => void;
  onClose: () => void;
  onOpenSettings: () => void;
  onPingWifi: () => void;
}

export default function TopBar(p: Props) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const iv = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(iv);
  }, []);

  const iconBtn =
    "grid place-items-center w-8 h-8 rounded-lg text-zinc-400 hover:text-accent hover:bg-accent-10 transition-all duration-200 cursor-pointer hover:shadow-glow-sm";

  return (
    <motion.header
      initial={{ y: -30, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 200, damping: 24 }}
      className="relative z-20 grid grid-cols-[1fr_auto_1fr] items-center h-16 shrink-0"
    >
      {/* logo */}
      <div className="flex items-center gap-3">
        <div className="relative w-9 h-9 grid place-items-center">
          <Hexagon className="absolute text-accent sp drop-accent" style={{ ["--dur" as string]: "9s" }} size={34} strokeWidth={1.3} />
          <span className="w-1.5 h-1.5 rounded-full bg-accent shadow-glow-sm breathe" />
        </div>
        <span className="font-orbitron text-xl font-bold tracking-[0.28em] grad-text text-glow select-none">
          NaiTRO
        </span>
        <span className="hidden md:inline font-mono2 text-[9px] tracking-[0.3em] text-zinc-600 mt-1">OS/2</span>
      </div>

      {/* clock */}
      <div className="text-center leading-none">
        <div className="font-orbitron text-2xl xl:text-[26px] font-semibold tracking-[0.22em] text-accent text-glow">
          {pad(now.getHours())}:{pad(now.getMinutes())}
          <motion.span
            key={now.getSeconds()}
            initial={{ opacity: 0.2, y: 3 }}
            animate={{ opacity: 1, y: 0 }}
            className="inline-block"
          >
            :{pad(now.getSeconds())}
          </motion.span>
        </div>
        <div className="font-mono2 text-[9px] tracking-[0.34em] text-zinc-500 mt-1.5">
          {now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" }).toUpperCase()}
        </div>
      </div>

      {/* right cluster */}
      <div className="flex items-center justify-end gap-1.5">
        <div className="hidden sm:flex items-center gap-2 mr-1">
          <span className="font-mono2 text-[9px] tracking-[0.3em] text-zinc-400">{p.status}</span>
          <span className="w-1.5 h-1.5 rounded-full bg-accent shadow-glow-sm breathe" />
          <span className="hairline-y h-6 mx-2" />
        </div>

        <button className={iconBtn} onClick={() => p.setVoice(!p.voice)} title="Voice">
          {p.voice ? <Mic size={15} className="text-accent" /> : <MicOff size={15} />}
        </button>
        <button className={iconBtn} onClick={p.onOpenSettings} title="Settings">
          <Settings size={15} className="transition-transform duration-500 hover:rotate-180" />
        </button>
        <button className={iconBtn} onClick={p.onPingWifi} title="Network">
          <Wifi size={15} />
        </button>
        <button className={`${iconBtn} hidden md:grid`} title="Audio">
          <Volume2 size={15} />
        </button>
        <button className={`${iconBtn} hidden md:grid`} title="Power">
          <BatteryMedium size={15} />
        </button>

        <span className="hairline-y h-6 mx-2" />

        <button className={iconBtn} onClick={p.onMinimize} title="Minimize">
          <Minus size={15} />
        </button>
        <button className={iconBtn} onClick={p.onMaximize} title="Maximize">
          <Square size={12} />
        </button>
        <button
          className="grid place-items-center w-8 h-8 rounded-lg text-zinc-400 hover:bg-red-500/90 hover:text-white transition-all duration-200 cursor-pointer hover:shadow-[0_0_16px_rgba(239,68,68,0.6)]"
          onClick={p.onClose}
          title="Close"
        >
          <X size={16} />
        </button>
      </div>
    </motion.header>
  );
}
