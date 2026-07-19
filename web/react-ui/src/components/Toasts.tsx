import { motion, AnimatePresence } from "framer-motion";
import { Zap } from "lucide-react";

export interface Toast {
  id: number;
  title: string;
  msg?: string;
}

export default function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="fixed bottom-6 right-6 z-[70] flex flex-col gap-2.5 items-end pointer-events-none">
      <AnimatePresence mode="popLayout">
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            layout
            initial={{ opacity: 0, x: 70, scale: 0.92 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 40, scale: 0.9, transition: { duration: 0.22 } }}
            transition={{ type: "spring", stiffness: 380, damping: 26 }}
            className="pointer-events-auto relative overflow-hidden glass-panel !rounded-xl pl-3 pr-4 py-2.5 flex items-center gap-3 min-w-[240px] max-w-[340px]"
          >
            <div className="grid place-items-center w-7 h-7 rounded-lg bg-accent-15 border border-accent-25 text-accent shrink-0">
              <Zap size={13} />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] font-semibold tracking-[0.14em] text-zinc-100 uppercase truncate">{t.title}</div>
              {t.msg && <div className="text-[10px] tracking-[0.06em] text-zinc-500 truncate">{t.msg}</div>}
            </div>
            <div className="absolute bottom-0 left-0 h-[2px] bg-accent shadow-glow-sm toastbar" />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
