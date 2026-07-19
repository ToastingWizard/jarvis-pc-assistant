import type { ReactNode } from "react";
import type { IconType } from "react-icons";
import { Plus } from "lucide-react";
import Reveal from "./Reveal";

interface Props {
  title: string;
  Icon: IconType;
  children: ReactNode;
  className?: string;
  i?: number;
  right?: ReactNode;
  onAdd?: () => void;
  addLabel?: string;
}

export default function Panel({ title, Icon, children, className = "", i = 0, right, onAdd, addLabel }: Props) {
  return (
    <Reveal i={i} className={`glass-panel group/panel overflow-hidden flex flex-col ${className}`}>
      <span className="corner corner-tl" /><span className="corner corner-tr" />
      <span className="corner corner-bl" /><span className="corner corner-br" />

      <header className="flex items-center justify-between px-5 pt-4">
        <div className="flex items-center gap-2.5">
          <span className="text-accent drop-accent transition-transform duration-300 group-hover/panel:scale-110 group-hover/panel:rotate-6">
            <Icon size={15} />
          </span>
          <h2 className="panel-title">{title}</h2>
        </div>
        {right}
      </header>

      <div className="hairline-x mx-5 mt-3.5" />

      <div className="px-5 py-4 flex-1 min-h-0">{children}</div>

      {onAdd && (
        <button
          onClick={onAdd}
          className="relative mb-3 mx-auto flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.3em] text-accent-dim hover:text-accent transition-all duration-300 hover:gap-3 hover:text-glow cursor-pointer"
        >
          <Plus size={11} className="transition-transform duration-300 group-hover/panel:rotate-90" />
          {addLabel}
        </button>
      )}
    </Reveal>
  );
}
