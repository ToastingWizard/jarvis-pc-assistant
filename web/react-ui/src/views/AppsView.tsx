import { useState } from "react";
import { motion } from "framer-motion";
import { Search, Plus, LayoutGrid } from "lucide-react";
import type { Ctx } from "../lib/types";
import AppTile from "../components/AppTile";
import Reveal from "../components/Reveal";

export default function AppsView({ ctx }: { ctx: Ctx }) {
  const [q, setQ] = useState("");
  const list = ctx.apps.filter((a) => a.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="flex flex-col h-full min-h-0">
      <Reveal i={0} className="flex items-center justify-between gap-4 mb-5 shrink-0">
        <div>
          <div className="flex items-center gap-3">
            <LayoutGrid size={18} className="text-accent drop-accent" />
            <h1 className="font-orbitron text-xl font-bold tracking-[0.3em] grad-text">APPLICATIONS</h1>
            <span className="font-mono2 text-[9px] tracking-[0.24em] px-2 py-1 rounded-md border border-accent-25 bg-accent-10 text-accent">
              {list.length} LOADED
            </span>
          </div>
          <p className="text-[12px] tracking-[0.08em] text-zinc-500 mt-2">Neural launcher — every binary one gesture away.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="FILTER…"
              className="jtext pl-8 pr-3 py-2 w-44 text-[11px] tracking-[0.18em] font-semibold"
            />
          </div>
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => ctx.openAdd("apps")}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-accent-15 border border-accent-40 text-accent text-[10px] font-semibold tracking-[0.26em] hover:shadow-glow transition-shadow cursor-pointer"
          >
            <Plus size={13} /> NEW
          </motion.button>
        </div>
      </Reveal>

      <div className="jscroll flex-1 min-h-0 overflow-y-auto pr-1 pb-2">
        {list.length === 0 ? (
          <div className="h-full grid place-items-center">
            <div className="text-center">
              <div className="font-orbitron text-zinc-600 tracking-[0.3em] text-sm">NO SIGNATURE MATCH</div>
              <div className="font-mono2 text-[10px] tracking-[0.2em] text-zinc-700 mt-2">TRY A DIFFERENT QUERY</div>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 xl:grid-cols-8 gap-y-8 gap-x-2 pt-2">
            {list.map((a, i) => (
              <AppTile
                key={a.id}
                tile={a}
                i={i}
                size={44}
                base={0.05}
                onLaunch={(n) => { ctx.pushToast("Launching " + n, "Allocating neural resources…"); ctx.runAction("app", n); }}
                onRemove={a.custom ? () => ctx.removeExtra("apps", a.id) : undefined}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
