import { useState } from "react";
import { motion, useMotionValue, useSpring, useTransform, AnimatePresence } from "framer-motion";
import GlitchText from "./GlitchText";

const ARCS = [
  { inset: "3%",  t: "2px",   sweep: "70deg",  dur: "16s", a: 0.95, rev: false },
  { inset: "8.5%",t: "3px",   sweep: "120deg", dur: "26s", a: 0.4,  rev: true  },
  { inset: "15%", t: "1.5px", sweep: "45deg",  dur: "10s", a: 1,    rev: false },
  { inset: "21%", t: "4px",   sweep: "200deg", dur: "40s", a: 0.22, rev: true  },
  { inset: "27%", t: "1.5px", sweep: "90deg",  dur: "13s", a: 0.7,  rev: true  },
  { inset: "32%", t: "2px",   sweep: "30deg",  dur: "7s",  a: 1,    rev: false },
];

const ORBITS = [
  { inset: "6%",  dur: "11s", d: 5, rev: false },
  { inset: "19%", dur: "19s", d: 4, rev: true  },
  { inset: "29%", dur: "8s",  d: 3, rev: false },
];

export default function NaitroCore({ parallax, onPulse }: { parallax: boolean; onPulse: () => void }) {
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const rx = useSpring(useTransform(my, [-0.5, 0.5], [7, -7]), { stiffness: 120, damping: 18 });
  const ry = useSpring(useTransform(mx, [-0.5, 0.5], [-7, 7]), { stiffness: 120, damping: 18 });
  const [burst, setBurst] = useState(0);

  const move = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!parallax) return;
    const r = e.currentTarget.getBoundingClientRect();
    mx.set((e.clientX - r.left) / r.width - 0.5);
    my.set((e.clientY - r.top) / r.height - 0.5);
  };
  const leave = () => { mx.set(0); my.set(0); };

  const pulse = () => {
    setBurst(Date.now());
    onPulse();
  };

  return (
    <div
      className="relative h-full w-full flex items-center justify-center select-none"
      onMouseMove={move}
      onMouseLeave={leave}
      style={{ perspective: 1000 }}
    >
      {/* ambient glow */}
      <div className="absolute w-[46%] aspect-square rounded-full bg-accent-20 blur-[90px] core-pulse pointer-events-none" />

      <motion.div
        style={parallax ? { rotateX: rx, rotateY: ry, transformStyle: "preserve-3d" } : undefined}
        className="relative aspect-square h-[86%] max-h-[430px] cursor-pointer"
        onClick={pulse}
        whileTap={{ scale: 0.96 }}
        initial={{ opacity: 0, scale: 0.7 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.25, type: "spring", stiffness: 120, damping: 16 }}
      >
        {/* crosshair axes */}
        <div className="absolute top-1/2 left-[-4%] right-[-4%] h-px bg-gradient-to-r from-transparent via-[rgb(var(--accent)/0.18)] to-transparent" />
        <div className="absolute left-1/2 top-[-4%] bottom-[-4%] w-px bg-gradient-to-b from-transparent via-[rgb(var(--accent)/0.18)] to-transparent" />

        {/* tick rings */}
        <svg viewBox="0 0 100 100" className="absolute inset-0 sp" style={{ ["--dur" as string]: "90s" }}>
          <circle cx="50" cy="50" r="48.6" fill="none" stroke="rgb(var(--accent) / 0.35)" strokeWidth="0.7" strokeDasharray="0.5 2.1" />
        </svg>
        <svg viewBox="0 0 100 100" className="absolute inset-0 sp sp-rev" style={{ ["--dur" as string]: "60s" }}>
          <circle cx="50" cy="50" r="45.5" fill="none" stroke="rgb(var(--accent) / 0.22)" strokeWidth="0.9" strokeDasharray="4 9" />
        </svg>

        {/* static hairline rings */}
        <div className="absolute inset-[1.5%] rounded-full border border-white/[0.05]" />
        <div className="absolute inset-[12%] rounded-full border border-white/[0.06]" />
        <div className="absolute inset-[24.5%] rounded-full border border-white/[0.07]" />
        <div className="absolute inset-[33.5%] rounded-full border border-accent-25" />

        {/* rotating conic arcs */}
        {ARCS.map((c, i) => (
          <div
            key={i}
            className={`arc sp ${c.rev ? "sp-rev" : ""}`}
            style={{
              inset: c.inset,
              ["--t" as string]: c.t,
              ["--sweep" as string]: c.sweep,
              ["--dur" as string]: c.dur,
              ["--a" as string]: c.a,
              ["--from" as string]: `${i * 80}deg`,
            }}
          />
        ))}

        {/* orbiting electrons */}
        {ORBITS.map((o, i) => (
          <div key={i} className={`orbit-dot ${o.rev ? "sp-rev" : ""}`} style={{ inset: o.inset, ["--dur" as string]: o.dur }}>
            <span style={{ width: o.d, height: o.d }} />
          </div>
        ))}

        {/* cardinal nodes */}
        {[0, 90, 180, 270].map((deg) => (
          <div key={deg} className="absolute inset-0" style={{ transform: `rotate(${deg}deg)` }}>
            <span className="absolute top-[0.8%] left-1/2 -translate-x-1/2 w-[5px] h-[5px] rounded-full bg-accent shadow-glow-sm breathe" style={{ animationDelay: `${deg / 90 * 0.5}s` }} />
          </div>
        ))}

        {/* sonar pings */}
        <div className="absolute inset-[30%] rounded-full border border-accent-40 sonar pointer-events-none" />
        <div className="absolute inset-[30%] rounded-full border border-accent-25 sonar pointer-events-none" style={{ animationDelay: "2s" }} />

        {/* click burst */}
        <AnimatePresence>
          {burst > 0 && (
            <motion.div
              key={burst}
              className="absolute inset-[20%] rounded-full border-2 border-accent-60 pointer-events-none"
              initial={{ scale: 0.6, opacity: 0.9 }}
              animate={{ scale: 2.4, opacity: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.9, ease: "easeOut" }}
              onAnimationComplete={() => setBurst(0)}
            />
          )}
        </AnimatePresence>

        {/* core disc */}
        <div
          className="absolute inset-[36%] rounded-full grid place-items-center core-pulse border border-accent-40 shadow-glow"
          style={{
            background:
              "radial-gradient(circle at 50% 38%, rgb(var(--accent) / 0.5), rgb(var(--accent) / 0.14) 52%, rgb(6 2 16 / 0.9) 78%)",
          }}
        >
          <div className="absolute inset-[6%] rounded-full border border-dashed border-accent-40 sp" style={{ ["--dur" as string]: "30s" }} />
          <div className="text-center relative z-10">
            <GlitchText
              text="NaiTRO"
              className="font-orbitron font-extrabold text-[clamp(18px,2.1vw,30px)] tracking-[0.32em] pl-[0.32em] text-white text-glow flicker"
            />
            <div className="font-mono2 text-[8px] tracking-[0.42em] pl-[0.42em] text-accent/80 mt-1.5">
              NEURAL CORE
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
