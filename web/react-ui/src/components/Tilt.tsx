import { motion, useMotionValue, useSpring } from "framer-motion";
import { useRef, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  max?: number;
  scale?: number;
  className?: string;
  enabled?: boolean;
  onClick?: () => void;
}

/**
 * Hover scale + moving specular glare.
 *
 * NOTE: this used to also do a 3D rotateX/rotateY tilt via
 * `transform-style: preserve-3d`. Dropped it -- WebKitGTK (what pywebview
 * uses on Linux) has a rendering bug where 3D transforms on an element
 * whose parent/child has `overflow: hidden` (true for ModeCard and the
 * app/folder/website tiles) can cause the content to flicker or vanish
 * entirely on hover. A plain 2D scale doesn't hit that bug and still
 * looks good.
 */
export default function Tilt({ children, scale = 1.05, className = "", enabled = true, onClick }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const hovered = useMotionValue(1);
  const scaleSpring = useSpring(hovered, { stiffness: 300, damping: 26, mass: 0.6 });

  const move = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!enabled || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    ref.current.style.setProperty("--gx", `${px * 100}%`);
    ref.current.style.setProperty("--gy", `${py * 100}%`);
  };
  const enter = () => hovered.set(scale);
  const leave = () => hovered.set(1);

  return (
    <motion.div
      ref={ref}
      onMouseMove={move}
      onMouseEnter={enter}
      onMouseLeave={leave}
      onClick={onClick}
      whileTap={{ scale: (enabled ? scale : 1) * 0.92 }}
      style={enabled ? { scale: scaleSpring } : undefined}
      className={`group relative ${className}`}
    >
      <div
        className="pointer-events-none absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"
        style={{ background: "radial-gradient(90px circle at var(--gx,50%) var(--gy,50%), rgb(255 255 255 / 0.14), transparent 65%)" }}
      />
      {children}
    </motion.div>
  );
}
