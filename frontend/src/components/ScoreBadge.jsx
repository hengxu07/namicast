import { getScoreColor, getScoreGradient } from '../utils/scoreColor';

// Circular score badge with SVG progress ring
// Usage: <ScoreBadge score={7.5} size="lg" />
export default function ScoreBadge({ score, size = 'md' }) {
  const { label } = getScoreColor(score);
  const color = getScoreGradient(score);

  // Size presets for sm / md / lg variants
  const sizes = {
    sm: { circle: 48, font: 16, label: 11 },
    md: { circle: 72, font: 24, label: 12 },
    lg: { circle: 96, font: 32, label: 13 },
  };
  const s = sizes[size];

  // SVG ring geometry
  const radius = (s.circle / 2) - 6;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 10) * circumference;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      {/* Rotate the SVG so the ring starts from the top */}
      <svg width={s.circle} height={s.circle} style={{ transform: 'rotate(-90deg)' }}>
        {/* Background track ring */}
        <circle
          cx={s.circle / 2} cy={s.circle / 2} r={radius}
          fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth={5}
        />
        {/* Animated foreground progress ring */}
        <circle
          cx={s.circle / 2} cy={s.circle / 2} r={radius}
          fill="none" stroke={color} strokeWidth={5}
          strokeDasharray={`${progress} ${circumference}`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 0.6s ease, stroke 0.6s ease' }}
        />
        {/* Score number — counter-rotated to stay upright */}
        <text
          x="50%" y="50%"
          dominantBaseline="middle" textAnchor="middle"
          fill={color}
          fontSize={s.font}
          fontWeight="700"
          style={{ transform: 'rotate(90deg)', transformOrigin: '50% 50%' }}
        >
          {score.toFixed(1)}
        </text>
      </svg>
      {/* Condition label below the ring */}
      <span style={{ color, fontSize: s.label, fontWeight: 600 }}>{label}</span>
    </div>
  );
}