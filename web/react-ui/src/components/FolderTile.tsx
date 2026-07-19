import { motion } from "framer-motion";
import { Folder, X } from "lucide-react";
import type { FolderItem } from "../lib/data";
import Reveal from "./Reveal";
import Tilt from "./Tilt";

interface Props {
  folder: FolderItem;
  i: number;
  size?: number;
  base?: number;
  nameSize?: string;
  onOpen: (id: string, name: string) => void;
  onRemove?: () => void;
}

export default function FolderTile({ folder, i, size = 38, base = 0.16, nameSize = "text-[11px]", onOpen, onRemove }: Props) {
  return (
    <Reveal i={i} base={base} className="relative">
      <Tilt onClick={() => onOpen(folder.id, folder.name)} className="flex flex-col items-center cursor-pointer select-none py-1">
        <div className="relative grid place-items-center" style={{ width: size + 22, height: size + 22 }}>
          <motion.div
            className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 blur-lg"
            style={{ background: `${folder.color}22` }}
          />
          <motion.div
            className="absolute inset-[4px] rounded-2xl border opacity-0 group-hover:opacity-100 transition-all duration-300 scale-90 group-hover:scale-100"
            style={{ borderColor: `${folder.color}44` }}
          />
          <Folder
            size={size}
            strokeWidth={1.3}
            style={{ color: folder.color, ["--fc" as string]: `${folder.color}aa` }}
            className="relative transition-all duration-300 group-hover:-translate-y-1.5 group-hover:scale-110 group-hover:drop-shadow-[0_0_10px_var(--fc)]"
          />
        </div>
        <span className={`mt-0.5 ${nameSize} font-medium tracking-wide text-zinc-400 group-hover:text-white transition-colors duration-200`}>
          {folder.name}
        </span>
      </Tilt>
      {onRemove && (
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="absolute top-0 right-0 z-10 grid place-items-center w-5 h-5 rounded-full bg-black/70 border border-white/15 text-zinc-500 hover:text-white hover:border-red-400/60 opacity-0 group-hover:opacity-100 transition-all duration-200 cursor-pointer"
        >
          <X size={10} />
        </button>
      )}
    </Reveal>
  );
}
