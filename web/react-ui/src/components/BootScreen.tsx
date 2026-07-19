import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Hexagon } from "lucide-react";

const STEPS = [
  "NaiTRO BIOS v2.0.1 — NEURAL QUANTUM INTERFACE",
  "VERIFYING NEURAL BANKS ................. OK",
  "LOADING INTERFACE MODULES .............. OK",
  "CALIBRATING ARC REACTOR ............... OK",
  "SYNCING NEURAL LACE ................... OK",
  "ESTABLISHING SECURE UPLINK ............ OK",
  "RENDERING DESKTOP ENVIRONMENT ......... OK",
];

export default function BootScreen({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0);
  const [prog, setProg] = useState(0);
  const doneRef = useRef(false);

  const finish = () => {
    if (doneRef.current) return;
    doneRef.current = true;
    onDone();
  };

  useEffect(() => {
    const iv = window.setInterval(
      () => setStep((s) => Math.min(s + 1, STEPS.length)),
      240
    );
    const iv2 = window.setInterval(() => {
      setProg((p) => {
        const n = Math.min(100, p + Math.random() * 8 + 2);
        if (n >= 100) {
          window.clearInterval(iv2);
          window.setTimeout(finish, 480);
        }
        return n;
      });
    }, 110);
    return () => {
      window.clearInterval(iv);
      window.clearInterval(iv2);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <motion.div
      className="fixed inset-0 z-[80] flex flex-col items-center justify-center bg-[#040109] cursor-pointer"
      onClick={finish}
      exit={{ opacity: 0, scale: 1.08, filter: "blur(8px)" }}
      transition={{ duration: 0.55, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* spinning mark */}
      <motion.div
        initial={{ opacity: 0, scale: 0.4 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.7, ease: "backOut" }}
        className="relative mb-10"
      >
        <Hexagon className="text-accent sp drop-accent" style={{ ["--dur" as string]: "7s" }} size={84} strokeWidth={1} />
        <Hexagon className="text-accent/40 sp sp-rev absolute inset-0" style={{ ["--dur" as string]: "12s" }} size={84} strokeWidth={0.6} />
        <div className="absolute inset-0 grid place-items-center">
          <div className="w-2.5 h-2.5 rounded-full bg-accent shadow-glow-sm breathe" />
        </div>
      </motion.div>

      <motion.h1
        initial={{ opacity: 0, letterSpacing: "1.2em" }}
        animate={{ opacity: 1, letterSpacing: "0.45em" }}
        transition={{ duration: 1.1, ease: "easeOut" }}
        className="font-orbitron text-3xl md:text-4xl font-extrabold grad-text text-glow pl-[0.45em]"
      >
        NaiTRO
      </motion.h1>
      <div className="font-mono2 text-[10px] tracking-[0.5em] text-zinc-500 mt-3 pl-[0.5em]">
        NEURAL OPERATING SYSTEM
      </div>

      {/* boot log */}
      <div className="mt-12 h-32 w-[min(88vw,460px)] font-mono2 text-[10px] md:text-[11px] leading-5 text-accent/70">
        {STEPS.slice(0, step).map((s, i) => (
          <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}>
            <span className="text-zinc-600 mr-2">{">"}</span>
            {s}
          </motion.div>
        ))}
        <span className="caret text-accent">▌</span>
      </div>

      {/* progress */}
      <div className="w-[min(88vw,460px)] mt-6">
        <div className="flex justify-between font-mono2 text-[10px] tracking-[0.3em] text-zinc-500 mb-2">
          <span>SYSTEM BOOT</span>
          <span className="text-accent">{Math.floor(prog)}%</span>
        </div>
        <div className="h-[3px] rounded-full bg-white/5 overflow-hidden">
          <div
            className="h-full rounded-full bg-accent shadow-glow-sm transition-[width] duration-150"
            style={{ width: `${prog}%` }}
          />
        </div>
        <div className="text-center font-mono2 text-[9px] tracking-[0.4em] text-zinc-600 mt-6">
          CLICK ANYWHERE TO SKIP
        </div>
      </div>
    </motion.div>
  );
}
