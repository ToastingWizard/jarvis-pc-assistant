import { useEffect, useState } from "react";

interface NaiTROCoreProps {
  state: "idle" | "listening" | "thinking" | "executing" | "speaking" | "error";
}

export default function NaiTROCore({ state }: NaiTROCoreProps) {
  const [rotation, setRotation] = useState(0);

  useEffect(() => {
    let speed = 0.5;
    if (state === "listening") speed = 2;
    if (state === "thinking") speed = 4;
    if (state === "speaking") speed = 3;

    const interval = setInterval(() => {
      setRotation((prev) => (prev + speed) % 360);
    }, 50);

    return () => clearInterval(interval);
  }, [state]);

  return (
    <div className={`naitro-core ${state}`}>
      {/* Rotating ring */}
      <div
        className="naitro-core-ring"
        style={{ transform: `rotate(${rotation}deg)` }}
      />

      {/* Inner circle with logo */}
      <div className="naitro-core-inner">
        <div className="naitro-logo-n">N</div>
      </div>

      {/* State indicator pulse */}
      {state !== "idle" && (
        <div className="absolute inset-0 rounded-full border-2 border-blue animate-ping opacity-20" />
      )}
    </div>
  );
}
