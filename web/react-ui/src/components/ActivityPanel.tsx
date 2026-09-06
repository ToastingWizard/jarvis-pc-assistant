import { Play, Volume2, MessageCircle, HelpCircle, ChevronRight } from "lucide-react";

const activities = [
  { icon: Play, text: "Opened YouTube", time: "2m ago" },
  { icon: Volume2, text: "Adjusted system volume", time: "5m ago" },
  { icon: MessageCircle, text: "Started Discord", time: "12m ago" },
  { icon: HelpCircle, text: "Answered user question", time: "18m ago" },
];

export default function ActivityPanel() {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-[rgb(var(--color-text-muted))]">
          Recent Activity
        </h3>
      </div>

      <div className="space-y-3">
        {activities.map((activity, i) => (
          <div key={i} className="flex items-center gap-3 text-sm">
            <activity.icon className="w-4 h-4 text-blue flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="truncate">{activity.text}</div>
            </div>
            <div className="text-xs text-[rgb(var(--color-text-muted))] flex-shrink-0">
              {activity.time}
            </div>
          </div>
        ))}
      </div>

      <button className="mt-4 w-full text-sm text-blue hover:text-blue/80 transition-colors flex items-center justify-center gap-1">
        View all
        <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  );
}
