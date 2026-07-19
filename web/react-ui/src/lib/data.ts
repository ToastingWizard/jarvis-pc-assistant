import type { IconType } from "react-icons";
import { VscVscode } from "react-icons/vsc";
import {
  SiSpotify, SiDiscord, SiTelegram, SiNotion, SiFigma, SiBlender, SiSteam,
  SiEpicgames, SiGmail, SiGoogledrive,
} from "react-icons/si";
import { PhotoshopIcon, PremiereIcon, AfterEffectsIcon } from "./brand";
import { FcGoogle } from "react-icons/fc";
import { FaYoutube, FaGithub, FaWikipediaW } from "react-icons/fa";
import {
  Terminal, Code2, Gamepad2, Music, Camera, PenTool, Cpu, Globe,
  Target, Briefcase, Clapperboard, Code,
} from "lucide-react";

export interface Tile {
  id: string;
  name: string;
  Icon: IconType;
  color: string;
  hex?: boolean; // renders an Orbitron letter instead of icon
  custom?: boolean;
}

export interface FolderItem {
  id: string;
  name: string;
  color: string;
  custom?: boolean;
}

/* ---------------- apps ---------------- */
export const APPS: Tile[] = [
  { id: "vscode",  name: "VS Code",      Icon: VscVscode,           color: "#22a2f0" },
  { id: "spotify", name: "Spotify",      Icon: SiSpotify,           color: "#1ed760" },
  { id: "discord", name: "Discord",      Icon: SiDiscord,           color: "#5b6cff" },
  { id: "telegram",name: "Telegram",     Icon: SiTelegram,          color: "#2aa1dd" },
  { id: "notion",  name: "Notion",       Icon: SiNotion,            color: "#ececf1" },
  { id: "ps",      name: "Photoshop",    Icon: PhotoshopIcon,       color: "#31a8ff" },
  { id: "pr",      name: "Premiere Pro", Icon: PremiereIcon,        color: "#d97cff" },
  { id: "ae",      name: "After Effects",Icon: AfterEffectsIcon,    color: "#9a9aff" },
  { id: "figma",   name: "Figma",        Icon: SiFigma,             color: "#1abcfe" },
  { id: "blender", name: "Blender",      Icon: SiBlender,           color: "#f5792a" },
  { id: "steam",   name: "Steam",        Icon: SiSteam,             color: "#c7d5e0" },
  { id: "epic",    name: "Epic Games",   Icon: SiEpicgames,         color: "#e8e8ec" },
];

export const APP_ICON_CHOICES: IconType[] = [
  Terminal, Code2, Gamepad2, Music, Camera, PenTool, Cpu, Globe,
];

/* ---------------- folders ---------------- */
export const FOLDERS: FolderItem[] = [
  { id: "work",      name: "Work",      color: "#c4b5fd" },
  { id: "college",   name: "College",   color: "#f0abfc" },
  { id: "projects",  name: "Projects",  color: "#a5b4fc" },
  { id: "resources", name: "Resources", color: "#99f6e4" },
  { id: "designs",   name: "Designs",   color: "#fbcfe8" },
  { id: "downloads", name: "Downloads", color: "#fde68a" },
];

export type FileKind = "doc" | "img" | "vid" | "arc" | "aud" | "code" | "file";
export interface FileItem { name: string; size: string; date: string; kind: FileKind }

export const FOLDER_FILES: Record<string, FileItem[]> = {
  work: [
    { name: "Q2_Report.pdf",      size: "2.4 MB", date: "MAY 12", kind: "doc" },
    { name: "Roadmap_2026.docx",  size: "812 KB", date: "MAY 09", kind: "doc" },
    { name: "Budget_Final.xlsx",  size: "1.1 MB", date: "APR 28", kind: "doc" },
    { name: "Pitch_Deck.key",     size: "48 MB",  date: "APR 21", kind: "file" },
  ],
  college: [
    { name: "Thesis_Draft_v4.pdf", size: "5.6 MB", date: "MAY 14", kind: "doc" },
    { name: "Linear_Algebra.pdf",  size: "9.2 MB", date: "MAY 02", kind: "doc" },
    { name: "lab_recording.mp4",   size: "240 MB", date: "APR 19", kind: "vid" },
    { name: "timetable.png",       size: "640 KB", date: "APR 02", kind: "img" },
  ],
  projects: [
    { name: "naitro-ui.zip",       size: "18 MB",  date: "MAY 15", kind: "arc" },
    { name: "neural_core.py",      size: "42 KB",  date: "MAY 15", kind: "code" },
    { name: "arc_reactor.tsx",     size: "12 KB",  date: "MAY 13", kind: "code" },
    { name: "README.md",           size: "4 KB",   date: "MAY 10", kind: "doc" },
  ],
  resources: [
    { name: "design_system.fig",   size: "22 MB",  date: "MAY 11", kind: "file" },
    { name: "ui_inspiration.mp4",  size: "96 MB",  date: "MAY 04", kind: "vid" },
    { name: "typescript_handbook.pdf", size: "12 MB", date: "APR 25", kind: "doc" },
  ],
  designs: [
    { name: "hero_0034.png",       size: "8.8 MB", date: "MAY 15", kind: "img" },
    { name: "brand_kit.zip",       size: "64 MB",  date: "MAY 08", kind: "arc" },
    { name: "motion_test.mov",     size: "310 MB", date: "APR 30", kind: "vid" },
    { name: "logo_final.svg",      size: "92 KB",  date: "APR 22", kind: "img" },
  ],
  downloads: [
    { name: "naitro_setup.pkg",    size: "1.2 GB", date: "MAY 16", kind: "arc" },
    { name: "reactor_loop.wav",    size: "36 MB",  date: "MAY 12", kind: "aud" },
    { name: "wallpaper_8k.png",    size: "48 MB",  date: "MAY 06", kind: "img" },
  ],
};

/* ---------------- websites ---------------- */
export const SITES: Tile[] = [
  { id: "google",    name: "Google",    Icon: FcGoogle,       color: "#e8e8ec" },
  { id: "youtube",   name: "YouTube",   Icon: FaYoutube,      color: "#ff3b3b" },
  { id: "github",    name: "GitHub",    Icon: FaGithub,       color: "#e8e8ec" },
  { id: "gmail",     name: "Gmail",     Icon: SiGmail,        color: "#ea4335" },
  { id: "drive",     name: "Drive",     Icon: SiGoogledrive,  color: "#0daf63" },
  { id: "wikipedia", name: "Wikipedia", Icon: FaWikipediaW,   color: "#e8e8ec" },
];

/* ---------------- modes ---------------- */
export interface Mode {
  id: string;
  name: string;
  desc: string;
  detail: string;
  Icon: IconType;
}
export const MODES: Mode[] = [
  { id: "focus",  name: "FOCUS MODE",       desc: "Minimize distractions.",  detail: "Silences notifications, dims ambient UI and primes a 45-minute deep-work sprint.",  Icon: Target },
  { id: "work",   name: "WORK MODE",        desc: "Boost productivity.",     detail: "Pins your IDE and comms, stages standup notes and enables quick capture everywhere.", Icon: Briefcase },
  { id: "fun",    name: "ENTERTAINMENT",    desc: "Relax and enjoy.",        detail: "Maxes the media engine, warms ambient lighting and pre-loads your streams.",          Icon: Clapperboard },
  { id: "dev",    name: "DEVELOPER MODE",   desc: "For dev environments.",   detail: "Spins up containers, mounts repos and tiles terminal, inspector and logs.",           Icon: Code },
];

/* ---------------- accents ---------------- */
export interface Accent { name: string; rgb: string }
export const ACCENTS: Accent[] = [
  { name: "HELIOTROPE", rgb: "168 85 247" },
  { name: "NEON CYAN",  rgb: "34 211 238" },
  { name: "MAGENTA",    rgb: "240 171 252" },
  { name: "EMERALD",    rgb: "52 211 153" },
  { name: "AMBER",      rgb: "251 191 36" },
];

export const SWATCHES = ["#a78bfa", "#f0abfc", "#67e8f9", "#6ee7b7", "#fcd34d", "#fda4af", "#93c5fd", "#e8e8ec"];
