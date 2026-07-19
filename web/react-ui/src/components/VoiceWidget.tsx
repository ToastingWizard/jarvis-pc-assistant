import { Mic, MicOff } from "lucide-react";
import { motion } from "framer-motion";

const BARS = 26;

export default function VoiceWidget({ active, onToggle }: { active: boolean; onToggle: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.6, type: "spring", stiffness: 260, damping: 22 }}
      className="glass-panel mx-1 p-3.5 cursor-pointer group"
      onClick={onToggle}
    >
      <div className="flex items-center gap-3">
        <motion.div
          whileHover={{ rotate: 12, scale: 1.12 }}
          className={`grid place-items-center w-9 h-9 rounded-xl border transition-all duration-300 ${
            active ? "border-accent-40 bg-accent-15 text-accent shadow-glow-sm" : "border-white/10 bg-white/5 text-zinc-500"
          }`}
        >
          {active ? <Mic size={16} /> : <MicOff size={16} />}
        </motion.div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${active ? "bg-accent breathe" : "bg-zinc-600"}`} />
            <span className={`text-[9px] font-semibold tracking-[0.3em] ${active ? "text-accent" : "text-zinc-500"}`}>
              {active ? "VOICE INPUT ACTIVE" : "VOICE OFFLINE"}
            </span>
          </div>
          <div className="text-[9px] tracking-[0.14em] text-zinc-600 mt-1 font-mono2">
            {active ? "SAY \"HEY NaiTRO\"" : "TAP TO ENABLE MIC"}
          </div>
        </div>
      </div>

      {/* waveform */}
      <div className="flex items-center gap-[3px] h-6 mt-3 px-1">
        {Array.from({ length: BARS }).map((_, i) => (
          <span
            key={i}
            className="w-[2.5px] rounded-full origin-center"
            style={
              active
                ? {
                    height: "100%",
                    background: `linear-gradient(180deg, rgb(var(--accent)), rgb(var(--accent) / 0.4))`,
                    boxShadow: "0 0 4px rgb(var(--accent) / 0.6)",
                    animation: `wave calc(${0.7 + (i % 5) * 0.13}s / var(--speed)) ease-in-out ${i * 0.055}s infinite`,
                    transform: "scaleY(0.3)",
                  }
                : { height: "22%", background: "#3f3f46" }
            }
          />
        ))}
      </div>
    </motion.div>
  );
}
