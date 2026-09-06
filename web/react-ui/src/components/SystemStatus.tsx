import { Cpu, HardDrive, Wifi, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";

export default function SystemStatus() {
  const [cpuUsage] = useState(12);
  const [memoryUsage] = useState(38);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-[rgb(var(--color-text-muted))]">
          System Status
        </h3>
        <span className="status-dot online" />
      </div>

      <div className="space-y-4">
        {/* CPU Usage */}
        <div>
          <div className="flex items-center justify-between text-sm mb-2">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-blue" />
              <span>CPU Usage</span>
            </div>
            <span className="text-blue font-mono">{cpuUsage}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${cpuUsage}%` }} />
          </div>
        </div>

        {/* Memory Usage */}
        <div>
          <div className="flex items-center justify-between text-sm mb-2">
            <div className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-blue" />
              <span>Memory Usage</span>
            </div>
            <span className="text-blue font-mono">{memoryUsage}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${memoryUsage}%` }} />
          </div>
        </div>

        {/* Network */}
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <Wifi className="w-4 h-4 text-blue" />
            <span>Network</span>
          </div>
          <span className="text-green-400">● Connected</span>
        </div>

        {/* Audio */}
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <Volume2 className="w-4 h-4 text-blue" />
            <span>Audio</span>
          </div>
          <span className="text-green-400">● Normal</span>
        </div>
      </div>
    </div>
  );
}
