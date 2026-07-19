import type { Tile, FolderItem } from "./data";

export type View = "dashboard" | "apps" | "folders" | "websites" | "modes" | "settings";
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
  removeExtra: (kind: AddKind, id: string) => void;
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
  speechStatus: { who: string; text: string } | null;
}
