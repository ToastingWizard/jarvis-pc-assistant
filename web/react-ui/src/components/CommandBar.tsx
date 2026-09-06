import { useState, useRef, KeyboardEvent } from "react";
import { Send, Mic } from "lucide-react";

interface CommandBarProps {
  onSubmit: (text: string) => void;
}

export default function CommandBar({ onSubmit }: CommandBarProps) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = () => {
    if (text.trim()) {
      onSubmit(text);
      setText("");
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleSubmit();
    }
  };

  return (
    <div className="command-bar">
      <Mic className="w-5 h-5 text-blue-dim" />
      <input
        ref={inputRef}
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type a command or speak..."
        className="flex-1"
      />
      <button
        onClick={handleSubmit}
        className="flex items-center justify-center w-10 h-10 rounded-lg bg-blue hover:bg-blue/80 transition-all"
        disabled={!text.trim()}
      >
        <Send className="w-5 h-5 text-white" />
      </button>
    </div>
  );
}
