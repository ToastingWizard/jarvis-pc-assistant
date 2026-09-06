import { Home, MessageSquare, Activity, Wrench, Settings, Mic, MicOff } from "lucide-react";

type View = "home" | "chat" | "activity" | "tools" | "settings";

interface NavigationProps {
  currentView: View;
  onViewChange: (view: View) => void;
  voiceEnabled: boolean;
  onToggleVoice: () => void;
}

const navItems: Array<{ id: View; icon: typeof Home; label: string }> = [
  { id: "home", icon: Home, label: "Home" },
  { id: "chat", icon: MessageSquare, label: "Chat" },
  { id: "activity", icon: Activity, label: "Activity" },
  { id: "tools", icon: Wrench, label: "Tools" },
  { id: "settings", icon: Settings, label: "Settings" },
];

export default function Navigation({ currentView, onViewChange, voiceEnabled, onToggleVoice }: NavigationProps) {
  return (
    <nav className="w-64 border-r border-[rgb(var(--color-border))] bg-[rgb(var(--color-bg-panel))] flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-[rgb(var(--color-border))]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue to-red flex items-center justify-center">
            <span className="text-white font-bold text-xl">N</span>
          </div>
          <div>
            <div className="text-lg font-bold font-display">NaiTRO</div>
            <div className="text-xs text-[rgb(var(--color-text-muted))]">AI Assistant</div>
          </div>
        </div>
      </div>

      {/* Navigation Items */}
      <div className="flex-1 p-4 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onViewChange(item.id)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
              currentView === item.id
                ? "bg-blue-10 text-blue"
                : "text-[rgb(var(--color-text-muted))] hover:bg-[rgb(var(--color-bg-elevated))] hover:text-[rgb(var(--color-text))]"
            }`}
          >
            <item.icon className="w-5 h-5" />
            <span className="text-sm font-medium">{item.label}</span>
          </button>
        ))}
      </div>

      {/* System Status Footer */}
      <div className="p-4 border-t border-[rgb(var(--color-border))]">
        {/* Voice Toggle */}
        <button
          onClick={onToggleVoice}
          className="w-full flex items-center gap-3 px-4 py-3 rounded-lg bg-[rgb(var(--color-bg-elevated))] hover:bg-[rgb(var(--color-bg-elevated))]/80 transition-all mb-3"
        >
          {voiceEnabled ? (
            <>
              <Mic className="w-5 h-5 text-blue" />
              <span className="text-sm font-medium">Voice Active</span>
            </>
          ) : (
            <>
              <MicOff className="w-5 h-5 text-[rgb(var(--color-text-muted))]" />
              <span className="text-sm font-medium">Voice Muted</span>
            </>
          )}
        </button>

        {/* Status Indicator */}
        <div className="flex items-center gap-2 px-4 py-2">
          <span className="status-dot online" />
          <div className="text-xs">
            <div className="font-medium">NaiTRO is ready</div>
            <div className="text-[rgb(var(--color-text-muted))]">All systems operational</div>
          </div>
        </div>

        {/* Subtle blue→red waveform indicator */}
        <div className="mt-3 h-1 rounded-full overflow-hidden bg-[rgb(var(--color-bg-elevated))]">
          <div className="h-full bg-gradient-to-r from-blue via-red to-blue animate-pulse" style={{ width: "60%" }} />
        </div>
      </div>
    </nav>
  );
}
