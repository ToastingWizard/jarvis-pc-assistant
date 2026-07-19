import { LayoutGrid, Folder, Globe, Zap, ArrowRight } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { MODES } from "../lib/data";
import type { Ctx } from "../lib/types";
import NaitroCore from "../components/NaitroCore";
import Panel from "../components/Panel";
import AppTile from "../components/AppTile";
import FolderTile from "../components/FolderTile";
import ModeCard from "../components/ModeCard";

export default function Dashboard({ ctx }: { ctx: Ctx }) {
  const launch = (name: string) => {
    ctx.pushToast("Launching " + name, "Allocating neural resources…");
    ctx.runAction("app", name);
  };

  return (
    <div className="flex flex-col min-h-full">
      {/* arc reactor */}
      <div className="h-[clamp(230px,35vh,410px)] shrink-0 relative">
        <NaitroCore
          parallax={ctx.parallax}
          onPulse={() => ctx.pushToast("Arc reactor ping", "Sometimes you gotta run before you can walk")}
        />
      </div>

      {/* conversation status -- what you said / what NaiTRO said, right under the logo */}
      <div className="h-[34px] shrink-0 flex items-center justify-center -mt-2 mb-2">
        <AnimatePresence mode="wait">
          {ctx.speechStatus && (
            <motion.div
              key={ctx.speechStatus.who + ctx.speechStatus.text}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.25 }}
              className="font-mono2 text-[11px] tracking-[0.08em] text-center max-w-[80%] truncate"
            >
              <span className="text-accent/90 font-semibold">{ctx.speechStatus.who}: </span>
              <span className="text-zinc-300">{ctx.speechStatus.text}</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="grid grid-cols-12 gap-4 xl:gap-5 pb-2">
        {/* apps */}
        <Panel
          title="APPS"
          Icon={LayoutGrid}
          i={1}
          className="col-span-12 lg:col-span-8"
          onAdd={() => ctx.openAdd("apps")}
          addLabel="ADD APP"
          right={
            <button
              onClick={() => ctx.setView("apps")}
              className="flex items-center gap-1 font-mono2 text-[9px] tracking-[0.26em] text-zinc-500 hover:text-accent transition-colors cursor-pointer group/link"
            >
              VIEW ALL
              <ArrowRight size={10} className="transition-transform duration-200 group-hover/link:translate-x-1" />
            </button>
          }
        >
          <div className="grid grid-cols-3 sm:grid-cols-4 xl:grid-cols-6 gap-y-4">
            {ctx.apps.slice(0, 12).map((a, i) => (
              <AppTile
                key={a.id}
                tile={a}
                i={i}
                base={0.2}
                onLaunch={launch}
                onRemove={a.custom ? () => ctx.removeExtra("apps", a.id) : undefined}
              />
            ))}
          </div>
        </Panel>

        {/* folders */}
        <Panel
          title="FOLDERS"
          Icon={Folder}
          i={2}
          className="col-span-12 lg:col-span-4"
          onAdd={() => ctx.openAdd("folders")}
          addLabel="ADD FOLDER"
        >
          <div className="grid grid-cols-3 gap-y-2">
            {ctx.folders.slice(0, 6).map((f, i) => (
              <FolderTile
                key={f.id}
                folder={f}
                i={i}
                base={0.26}
                onOpen={() => { ctx.setView("folders"); }}
                onRemove={f.custom ? () => ctx.removeExtra("folders", f.id) : undefined}
              />
            ))}
          </div>
        </Panel>

        {/* websites */}
        <Panel
          title="WEBSITES"
          Icon={Globe}
          i={3}
          className="col-span-12"
          onAdd={() => ctx.openAdd("sites")}
          addLabel="ADD WEBSITE"
          right={
            <button
              onClick={() => ctx.setView("websites")}
              className="flex items-center gap-1 font-mono2 text-[9px] tracking-[0.26em] text-zinc-500 hover:text-accent transition-colors cursor-pointer group/link"
            >
              VIEW ALL
              <ArrowRight size={10} className="transition-transform duration-200 group-hover/link:translate-x-1" />
            </button>
          }
        >
          <div className="flex flex-wrap justify-between gap-x-4 gap-y-4">
            {ctx.sites.slice(0, 8).map((s, i) => (
              <AppTile
                key={s.id}
                tile={s}
                i={i}
                base={0.3}
                size={34}
                onLaunch={(n) => { ctx.pushToast("Opening " + n, "Routing through secure uplink…"); ctx.runAction("website", n); }}
                onRemove={s.custom ? () => ctx.removeExtra("sites", s.id) : undefined}
              />
            ))}
          </div>
        </Panel>

        {/* modes */}
        <Panel title="MODES" Icon={Zap} i={4} className="col-span-12">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            {MODES.map((m, i) => (
              <ModeCard
                key={m.id}
                mode={m}
                i={i}
                base={0.3}
                active={ctx.activeMode === m.id}
                onToggle={() => {
                  const next = ctx.activeMode === m.id ? null : m.id;
                  ctx.setActiveMode(next);
                  ctx.pushToast(next ? `${m.name} ENGAGED` : "MODE DISENGAGED", next ? m.desc : "Returning to baseline systems");
                  if (next) ctx.runAction("mode", m.name);
                }}
              />
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
