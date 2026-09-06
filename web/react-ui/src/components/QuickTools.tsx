import { AppWindow, Globe, Layout, Settings } from "lucide-react";

export default function QuickTools() {
  const tools = [
    { icon: AppWindow, label: "Open App" },
    { icon: Globe, label: "Open Website" },
    { icon: Layout, label: "Control Windows" },
    { icon: Settings, label: "System Control" },
  ];

  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-wider text-[rgb(var(--color-text-muted))] mb-4">
        Quick Tools
      </h3>

      <div className="grid grid-cols-2 gap-2">
        {tools.map((tool, i) => (
          <button
            key={i}
            className="minimal-card p-3 flex flex-col items-center gap-2 clickable"
          >
            <tool.icon className="w-5 h-5 text-blue" />
            <span className="text-xs text-center">{tool.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
