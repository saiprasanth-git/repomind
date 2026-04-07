/**
 * RepoMind SVG logo — geometric brain/circuit mark.
 * Works at any size. Uses currentColor for theme compatibility.
 */
export function Logo({ size = 24, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-label="RepoMind"
      className={className}
    >
      {/* Outer hexagon — represents a repo/codebase container */}
      <path
        d="M16 2L28 9V23L16 30L4 23V9L16 2Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      {/* Inner circuit nodes */}
      <circle cx="16" cy="16" r="2.5" fill="currentColor" />
      <circle cx="10" cy="12" r="1.5" fill="currentColor" opacity="0.7" />
      <circle cx="22" cy="12" r="1.5" fill="currentColor" opacity="0.7" />
      <circle cx="10" cy="20" r="1.5" fill="currentColor" opacity="0.7" />
      <circle cx="22" cy="20" r="1.5" fill="currentColor" opacity="0.7" />
      {/* Connection lines */}
      <line x1="12" y1="13" x2="14" y2="15" stroke="currentColor" strokeWidth="1" opacity="0.5" />
      <line x1="20" y1="13" x2="18" y2="15" stroke="currentColor" strokeWidth="1" opacity="0.5" />
      <line x1="12" y1="19" x2="14" y2="17" stroke="currentColor" strokeWidth="1" opacity="0.5" />
      <line x1="20" y1="19" x2="18" y2="17" stroke="currentColor" strokeWidth="1" opacity="0.5" />
    </svg>
  );
}
