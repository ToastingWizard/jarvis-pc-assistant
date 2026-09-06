import { useCallback, useEffect, useState, useRef } from "react";
import { naitroApi, type DashboardData, type StatusData, onNaitroLog } from "./lib/api";
import { Home, MessageSquare, Activity, Wrench, Settings as SettingsIcon, Mic, MicOff } from "lucide-react";

// Core Components (to be created)
import NaiTROCore from "./components/NaiTROCore";
import CommandBar from "./components/CommandBar";
import QuickActions from "./components/QuickActions";
import SystemStatus from "./components/SystemStatus";
import ModelCard from "./components/ModelCard";
import QuickTools from "./components/QuickTools";
import ActivityPanel from "./components/ActivityPanel";
import Navigation from "./components/Navigation";

type View = "home" | "chat" | "activity" | "tools" | "settings";

export default function App() {
  const [view, setView] = useState<View>("home");
  const [data, setData] = useState<DashboardData | null>(null);
  const [status, setStatus] = useState<StatusData | null>(null);
  const [coreState, setCoreState] = useState<"idle" | "listening" | "thinking" | "executing" | "speaking" | "error">("idle");
  const [statusMessage, setStatusMessage] = useState("What can I do for you?");
  const [voiceEnabled, setVoiceEnabled] = useState(true);

  // Load dashboard data on mount
  useEffect(() => {
    const loadData = async () => {
      const dashboardData = await naitroApi.getDashboardData();
      if (dashboardData) {
        setData(dashboardData);
      }
    };
    loadData();
  }, []);

  // Poll status
  useEffect(() => {
    const pollStatus = async () => {
      const currentStatus = await naitroApi.getStatus();
      if (currentStatus) {
        setStatus(currentStatus);

        // Update core state based on status
        if (currentStatus.speaking) {
          setCoreState("speaking");
        } else if (currentStatus.conversation_active) {
          setCoreState("listening");
        } else if (currentStatus.listening) {
          setCoreState("idle");
        } else {
          setCoreState("idle");
        }
      }
    };

    pollStatus();
    const interval = setInterval(pollStatus, 500);
    return () => clearInterval(interval);
  }, []);

  // Listen to engine logs
  useEffect(() => {
    const unsubscribe = onNaitroLog((line) => {
      // Parse log lines
      const idx = line.indexOf(": ");
      if (idx !== -1) {
        const text = line.slice(idx + 2);
        setStatusMessage(text);
      }
    });
    return unsubscribe;
  }, []);

  const handleCommand = useCallback(async (text: string) => {
    if (!text.trim()) return;

    setCoreState("thinking");
    setStatusMessage("Processing...");

    const result = await naitroApi.sendCommand(text);

    if (result && !result.ok) {
      setCoreState("error");
      setStatusMessage(result.message || "Command failed");
      setTimeout(() => {
        setCoreState("idle");
        setStatusMessage("What can I do for you?");
      }, 3000);
    }
  }, []);

  const toggleVoice = useCallback(async () => {
    const newState = !voiceEnabled;
    setVoiceEnabled(newState);
    await naitroApi.toggleVoice(newState);
  }, [voiceEnabled]);

  const wakePhrase = data?.wake_phrase || "hey naitro";

  return (
    <div className="h-screen w-screen bg-gradient-to-br from-[rgb(8,8,12)] to-[rgb(12,12,18)] text-[rgb(var(--color-text))] overflow-hidden relative">
      {/* Subtle particle effect */}
      <div className="particle-field">
        <ParticleField />
      </div>

      {/* Noise overlay */}
      <div className="noise-overlay" />

      {/* Main Layout */}
      <div className="relative z-10 h-full flex">
        {/* Left Navigation */}
        <Navigation currentView={view} onViewChange={setView} voiceEnabled={voiceEnabled} onToggleVoice={toggleVoice} />

        {/* Center Main Area */}
        <main className="flex-1 flex flex-col items-center justify-center px-8 py-12 relative">
          {/* Wake Phrase Indicator */}
          <div className="absolute top-8 right-8 flex items-center gap-3 text-sm">
            <Mic className="w-4 h-4 text-blue" />
            <div>
              <div className="text-[rgb(var(--color-text-muted))] text-xs uppercase tracking-wider">Wake phrase</div>
              <div className="text-blue font-mono">&ldquo;{wakePhrase}&rdquo;</div>
            </div>
          </div>

          {/* NaiTRO Core */}
          <div className="mb-8">
            <NaiTROCore state={coreState} />
          </div>

          {/* Status */}
          <div className="text-center mb-12">
            <div className="text-2xl font-bold text-blue-dim mb-2 uppercase tracking-wider">
              {coreState === "idle" && "IDLE"}
              {coreState === "listening" && "LISTENING"}
              {coreState === "thinking" && "THINKING"}
              {coreState === "executing" && "EXECUTING"}
              {coreState === "speaking" && "SPEAKING"}
              {coreState === "error" && "ERROR"}
            </div>
            <div className="text-[rgb(var(--color-text-muted))]">{statusMessage}</div>
          </div>

          {/* Quick Actions */}
          <QuickActions onAction={handleCommand} />

          {/* Command Bar */}
          <div className="w-full max-w-2xl mt-12">
            <CommandBar onSubmit={handleCommand} />
          </div>
        </main>

        {/* Right System Panel */}
        <aside className="w-80 border-l border-[rgb(var(--color-border))] bg-[rgb(var(--color-bg-panel))] p-6 overflow-y-auto custom-scroll">
          {/* System Status */}
          <SystemStatus />

          {/* Divider */}
          <div className="divider-x my-6" />

          {/* Current AI Model */}
          <ModelCard />

          {/* Divider */}
          <div className="divider-x my-6" />

          {/* Quick Tools */}
          <QuickTools />

          {/* Divider */}
          <div className="divider-x my-6" />

          {/* Recent Activity */}
          <ActivityPanel />
        </aside>
      </div>
    </div>
  );
}

// Minimal particle effect component
function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationId: number;
    let particles: Array<{
      x: number;
      y: number;
      vx: number;
      vy: number;
      size: number;
      opacity: number;
    }> = [];

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;

      // Create particles (very sparse)
      const count = Math.floor((canvas.width * canvas.height) / 50000);
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        size: Math.random() * 1.5 + 0.5,
        opacity: Math.random() * 0.3 + 0.1,
      }));
    };

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(14, 165, 233, ${p.opacity})`; // Blue particles
        ctx.fill();
      });

      animationId = requestAnimationFrame(animate);
    };

    window.addEventListener("resize", resize);
    resize();
    animate();

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animationId);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0" />;
}
