import type { Tile, FolderItem } from "./data";
import type { ModeInfo } from "./api";

export type View = "dashboard" | "apps" | "folders" | "websites" | "modes" | "settings" | "browser";
export type AddKind = "apps" | "folders" | "sites";
export type Flag = "particles" | "scanlines" | "parallax" | "voice";

export interface ExtraItem {
  id: string;
  name: string;
  color: string;
  icon: number;
}

export interface Ctx {
  pushToast: (title: string, msg?: string) => void;
  setView: (v: View) => void;
  openAdd: (kind: AddKind) => void;
  removeItem: (kind: "app" | "folder" | "website", name: string, id?: string) => void;
  deleteMode: (name: string) => void;
  openModeBuilder: (mode?: ModeInfo | null) => void;
  runAction: (kind: "app" | "folder" | "website" | "mode", name: string) => void;
  parallax: boolean;
  voice: boolean;
  setVoice: (v: boolean) => void;
  activeMode: string | null;
  setActiveMode: (m: string | null) => void;
  accent: string;
  setAccent: (rgb: string) => void;
  speed: number;
  setSpeed: (n: number) => void;
  flags: Record<Flag, boolean>;
  toggleFlag: (f: Flag) => void;
  apps: Tile[];
  folders: FolderItem[];
  sites: Tile[];
  modes: ModeInfo[];
  speechStatus: { who: string; text: string } | null;
}
