import { Brain, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { naitroApi } from "../lib/api";

export default function ModelCard() {
  const [modelName, setModelName] = useState("Qwen2.5:7B (Ollama)");

  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-wider text-[rgb(var(--color-text-muted))] mb-4">
        Current AI Model
      </h3>

      <div className="minimal-card p-4 clickable">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-10 flex items-center justify-center">
              <Brain className="w-5 h-5 text-blue" />
            </div>
            <div>
              <div className="text-sm font-medium">{modelName}</div>
              <div className="text-xs text-[rgb(var(--color-text-muted))]">Click to change</div>
            </div>
          </div>
          <ChevronRight className="w-4 h-4 text-[rgb(var(--color-text-muted))]" />
        </div>
      </div>
    </div>
  );
}
