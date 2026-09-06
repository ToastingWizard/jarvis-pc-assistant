import { Globe, Newspaper, HelpCircle, Play } from "lucide-react";

interface QuickActionsProps {
  onAction: (command: string) => void;
}

const actions = [
  { icon: Play, label: "Open YouTube", command: "open youtube" },
  { icon: Globe, label: "Open Discord", command: "open discord" },
  { icon: Newspaper, label: "Check the news", command: "check the news" },
  { icon: HelpCircle, label: "What's my IP?", command: "what's my ip" },
];

export default function QuickActions({ onAction }: QuickActionsProps) {
  return (
    <div className="flex gap-3">
      {actions.map((action, i) => (
        <button
          key={i}
          onClick={() => onAction(action.command)}
          className="minimal-card px-4 py-3 flex items-center gap-2 clickable"
        >
          <action.icon className="w-4 h-4 text-blue" />
          <span className="text-sm">{action.label}</span>
        </button>
      ))}
    </div>
  );
}
