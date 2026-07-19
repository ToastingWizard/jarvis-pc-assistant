import type { IconBaseProps } from "react-icons";

/** Minimal Adobe-style app tile rendered as pure SVG (simple-icons dropped Adobe marks). */
const adobeTile =
  (bg: string, fg: string, letters: string) =>
  function AdobeIcon({ size = 24, style, className }: IconBaseProps) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        style={style}
        className={className}
        aria-hidden="true"
      >
        <rect x="0.6" y="0.6" width="22.8" height="22.8" rx="5.5" fill={bg} stroke={fg} strokeOpacity="0.85" strokeWidth="1.2" />
        <text
          x="12"
          y="16.3"
          textAnchor="middle"
          fontSize="10"
          fontWeight="800"
          fontFamily="Rajdhani, Arial, sans-serif"
          fill={fg}
          letterSpacing="0.5"
        >
          {letters}
        </text>
      </svg>
    );
  };

export const PhotoshopIcon = adobeTile("#032338", "#31a8ff", "Ps");
export const PremiereIcon = adobeTile("#1b0560", "#ea77ff", "Pr");
export const AfterEffectsIcon = adobeTile("#23235e", "#9e9eff", "Ae");
