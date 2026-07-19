import { motion } from "framer-motion";
import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  i?: number;          // stagger index
  base?: number;       // base delay
  y?: number;
  className?: string;
  onClick?: () => void;
}

/** Springy staggered entrance wrapper. */
export default function Reveal({ children, i = 0, base = 0.04, y = 18, className, onClick }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y, scale: 0.94 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: base + i * 0.045, type: "spring", stiffness: 320, damping: 26 }}
      className={className}
      onClick={onClick}
    >
      {children}
    </motion.div>
  );
}
