import { useEffect, useState } from "react";

export default function GlitchText({ text, className = "" }: { text: string; className?: string }) {
  const [on, setOn] = useState(false);

  useEffect(() => {
    let t1: number, t2: number;
    const loop = () => {
      t1 = window.setTimeout(() => {
        setOn(true);
        t2 = window.setTimeout(() => {
          setOn(false);
          loop();
        }, 320);
      }, 3800 + Math.random() * 4200);
    };
    loop();
    return () => { window.clearTimeout(t1); window.clearTimeout(t2); };
  }, []);

  return (
    <span className={`glitch ${on ? "on" : ""} ${className}`} data-text={text}>
      {text}
    </span>
  );
}
