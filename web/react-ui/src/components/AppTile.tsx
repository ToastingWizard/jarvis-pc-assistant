import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import type { Tile } from "../lib/data";
import Reveal from "./Reveal";
import Tilt from "./Tilt";

interface Props {
  tile: Tile;
  i: number;
  onLaunch?: (name: string) => void;
  onRemove?: () => void;
  size?: number;
  showName?: boolean;
  base?: number;
}

/** Brand icon tile with tilt, glow halo, launch ripple and specular glare. */
export default function AppTile({ tile, i, onLaunch, onRemove, size = 40, showName = true, base = 0.14 }: Props) {
  const [burst, setBurst] = useState(0);
  const { Icon } = tile;

  const launch = () => {
    setBurst(Date.now());
    onLaunch?.(tile.name);
  };

  return (
    <Reveal i={i} base={base} className="relative">
      <Tilt onClick={launch} className="flex flex-col items-center justify-start cursor-pointer select-none">
        <div
          className="relative grid place-items-center transition-all duration-300"
          style={{ width: size + 26, height: size + 26 }}
        >
          {/* hover halo */}
          <div
            className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-all duration-300 scale-75 group-hover:scale-100 blur-md"
            style={{ background: `${tile.color}30` }}
          />
          <div
            className="absolute inset-[5px] rounded-2xl border opacity-0 group-hover:opacity-100 transition-all duration-300 rotate-6 group-hover:rotate-0"
            style={{ borderColor: `${tile.color}55`, background: `linear-gradient(160deg, ${tile.color}14, transparent 60%)` }}
          />
          {/* icon */}
          <span
            className="relative transition-all duration-300 group-hover:-translate-y-1.5 group-hover:scale-110 group-hover:drop-shadow-[0_0_14px_var(--tc)]"
            style={{ color: tile.color, ["--tc" as string]: `${tile.color}aa` }}
          >
            {tile.hex ? (
              <span
                className="grid place-items-center rounded-xl font-orbitron font-bold"
                style={{
                  width: size, height: size,
                  background: `linear-gradient(160deg, ${tile.color}33, ${tile.color}0d)`,
                  border: `1px solid ${tile.color}66`,
                  color: tile.color,
                  fontSize: size * 0.44,
                  textShadow: `0 0 12px ${tile.color}`,
                }}
              >
                {tile.name.charAt(0).toUpperCase()}
              </span>
            ) : (
              <Icon size={size} />
            )}
          </span>

          {/* launch ripple */}
          <AnimatePresence>
            {burst > 0 && (
              <motion.div
                key={burst}
                className="absolute inset-0 rounded-2xl border-2"
                style={{ borderColor: tile.color }}
                initial={{ opacity: 0.9, scale: 0.7 }}
                animate={{ opacity: 0, scale: 1.6 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.55, ease: "easeOut" }}
                onAnimationComplete={() => setBurst(0)}
              />
            )}
          </AnimatePresence>
        </div>

        {showName && (
          <span className="mt-1 text-[11px] font-medium tracking-wide text-zinc-400 group-hover:text-white transition-colors duration-200 whitespace-nowrap">
            {tile.name}
          </span>
        )}
      </Tilt>

      {onRemove && (
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="absolute -top-1 right-1 z-10 grid place-items-center w-5 h-5 rounded-full bg-black/70 border border-white/15 text-zinc-500 hover:text-white hover:border-red-400/60 hover:shadow-[0_0_10px_rgba(248,113,113,0.5)] opacity-0 group-hover:opacity-100 transition-all duration-200 cursor-pointer"
        >
          <X size={10} />
        </button>
      )}
    </Reveal>
  );
}
