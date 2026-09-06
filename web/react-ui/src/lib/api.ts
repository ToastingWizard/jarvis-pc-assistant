/**
 * NaiTRO REST API Client
 * Connects to localhost HTTP server instead of PyWebView bridge
 */

const API_BASE = import.meta.env.DEV ? "http://localhost:8080" : "";

// Helper to check if running in development mode with mock data
const isMockMode = () => {
  return import.meta.env.DEV && !window.location.host.includes("localhost:8080");
};

// Mock data for preview/development
const MOCK_DATA = {
  wake_phrase: "hey naitro",
  user_title: "sir",
  allow_push: false,
  speak_responses: true,
  ai_status: { has_nvidia: false, has_gemini: false },
  apps: {
    "Chrome": { icon: null, available: true },
    "Spotify": { icon: null, available: true },
    "Discord": { icon: null, available: true },
  },
  folders: {
    "Downloads": {},
    "Desktop": {},
  },
  websites: {
    "YouTube": {},
    "Google": {},
    "Netflix": {},
  },
  modes: {
    "Chill Mode": { name: "Chill Mode", desc: "2 steps", steps: [], style: "" },
  },
  active_mode: null,
  picker: { apps: [], websites: [], folders: [], playlists: [] },
};

async function apiCall<T>(endpoint: string, options?: RequestInit): Promise<T | null> {
  if (isMockMode()) {
    console.log("[Mock API]", endpoint, options);
    return null;
  }

  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      console.error(`API error: ${response.status} ${response.statusText}`);
      return null;
    }

    return await response.json();
  } catch (error) {
    console.error("API call failed:", error);
    return null;
  }
}

export interface DashboardData {
  wake_phrase: string;
  user_title: string;
  allow_push: boolean;
  speak_responses: boolean;
  ai_status: {
    has_nvidia: boolean;
    has_gemini: boolean;
  };
  apps: Record<string, { icon?: string | null; available: boolean }>;
  folders: Record<string, unknown>;
  websites: Record<string, unknown>;
  modes: Record<string, ModeInfo>;
  active_mode: string | null;
  picker: {
    apps: string[];
    websites: string[];
    folders: string[];
    playlists: string[];
  };
}

export interface ModeInfo {
  name: string;
  desc: string;
  steps: Array<{
    type: "app" | "website" | "folder" | "playlist";
    name: string;
    url?: string;
    delay?: number;
  }>;
  style: string;
}

export interface StatusData {
  speaking: boolean;
  listening: boolean;
  conversation_active: boolean;
  voice_error: string | null;
}

export interface ActionResult {
  ok: boolean;
  message: string;
}

export const naitroApi = {
  async getDashboardData(): Promise<DashboardData | null> {
    if (isMockMode()) return MOCK_DATA;
    return apiCall<DashboardData>("/api/dashboard");
  },

  async runAction(kind: string, name: string): Promise<ActionResult | null> {
    return apiCall<ActionResult>(`/api/action?kind=${kind}&name=${encodeURIComponent(name)}`, {
      method: "POST",
    });
  },

  async sendCommand(text: string): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/command", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },

  async addItem(kind: string, name: string, target: string): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/item/add", {
      method: "POST",
      body: JSON.stringify({ kind, name, target }),
    });
  },

  async removeItem(kind: string, name: string): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/item/remove", {
      method: "POST",
      body: JSON.stringify({ kind, name }),
    });
  },

  async saveMode(name: string, steps: ModeInfo["steps"], style: string): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/mode/save", {
      method: "POST",
      body: JSON.stringify({ name, steps, style }),
    });
  },

  async deleteMode(name: string): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/mode/delete", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  },

  async deactivateMode(): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/mode/deactivate", {
      method: "POST",
    });
  },

  async setSetting(key: string, value: boolean | string): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/setting", {
      method: "POST",
      body: JSON.stringify({ key, value }),
    });
  },

  async toggleVoice(on: boolean): Promise<ActionResult | null> {
    return apiCall<ActionResult>(`/api/voice/toggle?on=${on}`, {
      method: "POST",
    });
  },

  async saveAIConfig(provider: string, key: string): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/ai/config", {
      method: "POST",
      body: JSON.stringify({ provider, key }),
    });
  },

  async getStatus(): Promise<StatusData | null> {
    if (isMockMode()) {
      return { speaking: false, listening: false, conversation_active: false, voice_error: null };
    }
    return apiCall<StatusData>("/api/status");
  },

  // Browser agent methods
  async browserStatus(): Promise<any> {
    return apiCall("/api/browser/status");
  },

  async browserStart(): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/browser/start", { method: "POST" });
  },

  async browserStop(): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/browser/stop", { method: "POST" });
  },

  async browserCommand(text: string): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/browser/command", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },

  async browserExecute(action: any): Promise<ActionResult | null> {
    return apiCall<ActionResult>("/api/browser/execute", {
      method: "POST",
      body: JSON.stringify({ action }),
    });
  },
};

// Log streaming (via EventSource or polling)
// The backend can push logs to the frontend
let logCallback: ((line: string) => void) | null = null;
let logPollInterval: number | null = null;

export function onNaitroLog(callback: (line: string) => void): () => void {
  logCallback = callback;

  // For now, logs come through the engine's internal mechanism
  // In a future enhancement, this could use Server-Sent Events (SSE)
  // or WebSocket for real-time log streaming

  return () => {
    logCallback = null;
  };
}

// Helper to emit logs from the engine (called by backend via some mechanism)
if (typeof window !== "undefined") {
  (window as any).naitroLog = (line: string) => {
    if (logCallback) {
      logCallback(line);
    }
  };
}
