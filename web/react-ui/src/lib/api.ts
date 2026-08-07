/**
 * api.ts — bridge between the React UI and NaitroEngine, via
 * webview_ui.py's Api class (window.pywebview.api.*).
 *
 * Falls back to a small in-browser mock when opened outside pywebview
 * (e.g. `npm run dev` in a normal browser), so the UI is still previewable
 * without the Python backend running.
 */

export interface ModeStep {
  type: "app" | "website" | "folder" | "playlist";
  name?: string;
  url?: string;
  delay?: number;
}

export interface ModeInfo {
  name: string; // config key, e.g. "chill mode"
  desc: string; // "2 steps" | "AI personality"
  steps: ModeStep[];
  style: string; // optional AI personality; "" when none
}

export interface AiStatus {
  has_nvidia: boolean; // an NVIDIA NIM key is configured
  has_gemini: boolean; // a Gemini key is configured
}

export interface DashboardData {
  wake_phrase: string;
  user_title: string;
  allow_push: boolean;
  speak_responses: boolean;
  ai_status: AiStatus;
  apps: Record<string, { icon?: string; available?: boolean }>;
  folders: Record<string, object>;
  websites: Record<string, object>;
  modes: Record<string, ModeInfo>;
  active_mode: string | null;
  picker: { apps: string[]; websites: string[]; folders: string[]; playlists: string[] };
}

export interface ActionResult {
  ok: boolean;
  message: string;
}

export interface BrowserTab {
  tab_id: string;
  page_id: number;
  url: string;
  title: string;
  is_active: boolean;
}

export interface BrowserSnapshot {
  url: string;
  title: string;
  visible_text: string;
  links: Array<{ text: string; href: string }>;
  buttons: Array<{ text: string; tag: string }>;
  forms: unknown[];
}

export interface BrowserStatus {
  running: boolean;
  tabs: BrowserTab[];
  current_snapshot: BrowserSnapshot | null;
  last_action: string;
  pending_confirmation: unknown | null;
}

export interface BrowserRunResult {
  ok: boolean;
  message: string;
  thought: string;
  actions: unknown[];
  error: string | null;
  snapshot: BrowserSnapshot | null;
  confirmation_required?: boolean;
  pending_action?: unknown;
}

export interface EngineStatus {
  speaking: boolean;
  listening: boolean;
  conversation_active: boolean;
  voice_error: string | null; // "mic" when the mic can't be opened; null when healthy
}

declare global {
  interface Window {
    pywebview?: { api: Record<string, (...args: unknown[]) => Promise<unknown>> };
    naitroLog?: (line: string) => void;
  }
}

const hasApi = () => typeof window.pywebview !== "undefined" && !!window.pywebview.api;

async function call<T>(name: string, ...args: unknown[]): Promise<T | null> {
  if (hasApi()) {
    try {
      return (await window.pywebview!.api[name](...args)) as T;
    } catch (e) {
      console.error(`[api] ${name} failed:`, e);
      return null;
    }
  }
  console.log("[api mock]", name, args);
  return mock<T>(name);
}

const MOCK_DASHBOARD: DashboardData = {
  wake_phrase: "hey naitro",
  user_title: "sir",
  allow_push: true,
  speak_responses: true,
  ai_status: { has_nvidia: false, has_gemini: false },
  apps: { Notepad: {}, Calculator: {}, Chrome: {}, Spotify: {} },
  folders: { Downloads: {}, Desktop: {}, Documents: {} },
  websites: { Youtube: {}, Google: {}, Netflix: {} },
  modes: {
    "chill mode": {
      name: "chill mode",
      desc: "2 steps",
      steps: [
        { type: "app", name: "chrome", delay: 1 },
        { type: "website", name: "netflix" },
      ],
      style: "",
    },
  },
  active_mode: null,
  picker: { apps: ["notepad", "chrome", "spotify"], websites: ["youtube", "netflix"], folders: ["downloads"], playlists: ["liked songs"] },
};

function mock<T>(name: string): T | null {
  if (name === "get_dashboard_data") return MOCK_DASHBOARD as unknown as T;
  if (name === "get_status") return { speaking: false, listening: false, conversation_active: false, voice_error: null } as unknown as T;
  return { ok: true, message: "(preview mode — no engine attached)" } as unknown as T;
}

export const naitroApi = {
  getDashboardData: () => call<DashboardData>("get_dashboard_data"),
  runAction: (kind: "app" | "folder" | "website" | "mode", name: string) =>
    call<ActionResult>("run_action", kind, name),
  sendCommand: (text: string) => call<ActionResult>("send_command", text),
  addItem: (kind: "app" | "folder" | "website", name: string, target: string) =>
    call<ActionResult>("add_item", kind, name, target),
  removeItem: (kind: "app" | "folder" | "website" | "playlist", name: string) =>
    call<ActionResult>("remove_item", kind, name),
  saveMode: (name: string, steps: ModeStep[], style: string) =>
    call<ActionResult>("save_mode", name, steps, style),
  deleteMode: (name: string) => call<ActionResult>("delete_mode", name),
  deactivateMode: () => call<ActionResult>("deactivate_mode"),
  setSetting: (key: string, value: boolean) => call<ActionResult>("set_setting", key, value),
  saveAiConfig: (provider: "nvidia" | "gemini", key: string) =>
    call<ActionResult>("save_ai_config", provider, key),
  toggleVoice: (on: boolean) => call<ActionResult>("toggle_voice", on),
  getStatus: () => call<EngineStatus>("get_status"),
  minimize: () => call("minimize"),
  close: () => call("close"),
  browserStatus: () => call<BrowserStatus>("browser_status"),
  browserStart: () => call<ActionResult>("browser_start"),
  browserStop: () => call<ActionResult>("browser_stop"),
  browserCommand: (text: string) => call<BrowserRunResult>("browser_command", text),
  browserTabs: () => call<{ tabs: BrowserTab[]; current_snapshot: BrowserSnapshot | null }>("browser_tabs"),
  browserExecute: (action: object) => call<ActionResult>("browser_execute", action),
};

/** Subscribe to engine.log() output (window.naitroLog is called by
 * webview_ui.py's log bridge). Returns an unsubscribe function. */
export function onNaitroLog(handler: (line: string) => void): () => void {
  window.naitroLog = handler;
  return () => {
    if (window.naitroLog === handler) delete window.naitroLog;
  };
}
