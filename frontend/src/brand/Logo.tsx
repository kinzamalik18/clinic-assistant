// Brightside Dental mark: a tooth cut out of a sun, with three rays.
// Keep public/favicon.svg in sync with this drawing.

const TOOTH =
  "M15 13.5c-2.6 0-4.3 2-4.3 4.9 0 3.6 1.7 5.4 2.6 9.1.6 2.4 1.1 4.2 2.3 4.2 1.4 0 1.7-2.4 2.4-4.7.4-1.4 1-2.4 2.6-2.4s2.2 1 2.6 2.4c.7 2.3 1 4.7 2.4 4.7 1.2 0 1.7-1.8 2.3-4.2.9-3.7 2.6-5.5 2.6-9.1 0-2.9-1.7-4.9-4.3-4.9-1.9 0-3.1 1.2-4.8 1.2S16.9 13.5 15 13.5z";

export function LogoMark({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" className="shrink-0">
      <circle cx="20" cy="23" r="15" className="fill-sage" />
      <path d={TOOTH} className="fill-enamel" />
      <path
        d="M20 1.8v3M9.6 5.6l1.9 2.4M30.4 5.6l-1.9 2.4"
        className="stroke-ray"
        strokeWidth="2.2"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

export function Logo({ size = 36 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={size} />
      <span className="font-display text-xl font-bold tracking-tight">Brightside Dental</span>
    </span>
  );
}
