import { useEffect, useRef } from "react";

interface P {
  x: number; y: number; vx: number; vy: number; r: number; a: number;
}

export default function ParticleField({ rgb, enabled }: { rgb: string; enabled: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const mouse = useRef({ x: -9999, y: -9999 });

  useEffect(() => {
    if (!enabled) return;
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    const DPR = Math.min(2, window.devicePixelRatio || 1);
    let w = 0, h = 0, raf = 0;
    let parts: P[] = [];
    const [r, g, b] = rgb.split(" ").map(Number);

    const resize = () => {
      w = canvas.width = window.innerWidth * DPR;
      h = canvas.height = window.innerHeight * DPR;
      canvas.style.width = window.innerWidth + "px";
      canvas.style.height = window.innerHeight + "px";
      const count = Math.floor((window.innerWidth * window.innerHeight) / 26000);
      parts = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.18 * DPR,
        vy: (Math.random() - 0.5) * 0.18 * DPR - 0.06 * DPR,
        r: (Math.random() * 1.4 + 0.4) * DPR,
        a: Math.random() * 0.5 + 0.15,
      }));
    };
    resize();
    window.addEventListener("resize", resize);

    const onMove = (e: PointerEvent) => {
      mouse.current.x = e.clientX * DPR;
      mouse.current.y = e.clientY * DPR;
    };
    window.addEventListener("pointermove", onMove);

    const link = 110 * DPR;
    const loop = () => {
      ctx.clearRect(0, 0, w, h);
      for (const p of parts) {
        const dx = p.x - mouse.current.x;
        const dy = p.y - mouse.current.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < link * link && d2 > 1) {
          const d = Math.sqrt(d2);
          p.vx += (dx / d) * 0.012 * DPR;
          p.vy += (dy / d) * 0.012 * DPR;
        }
        p.vx *= 0.985; p.vy *= 0.985;
        p.x += p.vx; p.y += p.vy;
        if (p.x < -10) p.x = w + 10; if (p.x > w + 10) p.x = -10;
        if (p.y < -10) p.y = h + 10; if (p.y > h + 10) p.y = -10;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r},${g},${b},${p.a * 0.5})`;
        ctx.fill();
      }
      for (let i = 0; i < parts.length; i++) {
        for (let j = i + 1; j < parts.length; j++) {
          const a = parts[i], c = parts[j];
          const dx = a.x - c.x, dy = a.y - c.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < link * link) {
            const o = (1 - Math.sqrt(d2) / link) * 0.09;
            ctx.strokeStyle = `rgba(${r},${g},${b},${o})`;
            ctx.lineWidth = DPR * 0.6;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(c.x, c.y);
            ctx.stroke();
          }
        }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onMove);
    };
  }, [rgb, enabled]);

  if (!enabled) return null;
  return <canvas ref={ref} className="fixed inset-0 pointer-events-none opacity-70" style={{ zIndex: 0 }} />;
}
