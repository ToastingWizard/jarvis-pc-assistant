/**
 * api.ts — bridge between the React UI and NaitroEngine, via
 * webview_ui.py's Api class (window.pywebview.api.*).
 *
 * Falls back to a small in-browser mock when opened outside pywebview
 * (e.g. `npm run dev` in a normal browser), so the UI is still previewable
 * without the Python backend running.
 */

export interface DashboardData {
  wake_phrase: string;
  user_title: string;
  allow_push: boolean;
  speak_responses: boolean;
  apps: Record<string, object>;
  folders: Record<string, object>;
  websites: Record<string, object>;
  modes: Record<string, { desc: string }>;
}

export interface ActionResult {
  ok: boolean;
  message: string;
}

export interface EngineStatus {
  speaking: boolean;
  listening: boolean;
  conversation_active: boolean;
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
  apps: { Notepad: {}, Calculator: {}, Chrome: {}, Spotify: {} },
  folders: { Downloads: {}, Desktop: {}, Documents: {} },
  websites: { Youtube: {}, Google: {}, Netflix: {} },
  modes: { "Chill Mode": { desc: "2 steps" } },
};

function mock<T>(name: string): T | null {
  if (name === "get_dashboard_data") return MOCK_DASHBOARD as unknown as T;
  if (name === "get_status") return { speaking: false, listening: false, conversation_active: false } as unknown as T;
  return { ok: true, message: "(preview mode — no engine attached)" } as unknown as T;
}

export const naitroApi = {
  getDashboardData: () => call<DashboardData>("get_dashboard_data"),
  runAction: (kind: "app" | "folder" | "website" | "mode", name: string) =>
    call<ActionResult>("run_action", kind, name),
  sendCommand: (text: string) => call<ActionResult>("send_command", text),
  addItem: (kind: "app" | "folder" | "website", name: string, target: string) =>
    call<ActionResult>("add_item", kind, name, target),
  setSetting: (key: string, value: boolean) => call<ActionResult>("set_setting", key, value),
  toggleVoice: (on: boolean) => call<ActionResult>("toggle_voice", on),
  getStatus: () => call<EngineStatus>("get_status"),
  minimize: () => call("minimize"),
  close: () => call("close"),
};

/** Subscribe to engine.log() output (window.naitroLog is called by
 * webview_ui.py's log bridge). Returns an unsubscribe function. */
export function onNaitroLog(handler: (line: string) => void): () => void {
  window.naitroLog = handler;
  return () => {
    if (window.naitroLog === handler) delete window.naitroLog;
  };
}
