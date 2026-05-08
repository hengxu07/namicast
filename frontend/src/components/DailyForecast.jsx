import { getScoreGradient } from '../utils/scoreColor';

function DailyForecast({ forecasts, convert }) {
  if (!forecasts || forecasts.length === 0) return null;

  const sessionIcons = {
    'Dawn patrol': '🌅',
    'Morning': '☀️',
    'Afternoon': '🌤',
    'Evening': '🌇',
  };

  const verdictColors = {
    Excellent: { bg: '#EAF3DE', color: '#3B6D11' },
    Good: { bg: '#E1F5EE', color: '#0F6E56' },
    Fair: { bg: '#FAEEDA', color: '#854F0B' },
    Poor: { bg: '#FCEBEB', color: '#A32D2D' },
  };

  return (
    <div style={s.container}>
      <div style={s.title}>Today's sessions</div>
      <div style={s.grid}>
        {forecasts.map((session, i) => {
          const scoreColor = getScoreGradient(session.score);
          return (
            <div key={i} style={{
              ...s.card,
              ...(session.best ? s.cardBest : {}),
              borderLeft: `4px solid ${scoreColor}`, // Color-coded left border
            }}>
              {session.best && <div style={s.bestBadge}>Best</div>}
              <div style={s.sessionName}>
                {sessionIcons[session.name] || '🌊'} {session.name}
              </div>
              <div style={s.sessionTime}>{session.time}</div>

              {/* Score number color matches the gradient */}
              <div style={{ ...s.score, color: scoreColor }}>
                {session.score}<span style={s.scoreMax}>/10</span>
              </div>

              <div style={{
                ...s.verdict,
                background: verdictColors[session.verdict]?.bg,
                color: verdictColors[session.verdict]?.color,
              }}>
                {session.verdict}
              </div>
              <div style={s.metrics}>
                <div style={s.metricRow}>
                  <span style={s.metricLabel}>Waves</span>
                  <span style={s.metricValue}>{convert.height(session.waveHeight)}</span>
                </div>
                <div style={s.metricRow}>
                  <span style={s.metricLabel}>Wind</span>
                  <span style={s.metricValue}>{convert.speed(session.windSpeed)} {session.windDirection}</span>
                </div>
                <div style={s.metricRow}>
                  <span style={s.metricLabel}>Period</span>
                  <span style={s.metricValue}>{session.wavePeriod}s</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const s = {
  container: { marginBottom: '16px' },
  title: { fontSize: '14px', fontWeight: '500', color: '#042C53', marginBottom: '12px' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px' },
  card: { background: '#fff', borderRadius: '12px', padding: '16px', border: '0.5px solid #B5D4F4', position: 'relative' },
  cardBest: { border: '2px solid #378ADD' },
  bestBadge: { position: 'absolute', top: '-10px', left: '50%', transform: 'translateX(-50%)', background: '#378ADD', color: '#fff', fontSize: '11px', padding: '2px 10px', borderRadius: '20px' },
  sessionName: { fontSize: '13px', fontWeight: '500', color: '#042C53', marginBottom: '2px' },
  sessionTime: { fontSize: '11px', color: '#378ADD', marginBottom: '10px' },
  score: { fontSize: '32px', fontWeight: '500', lineHeight: '1', marginBottom: '6px' }, // color removed — set dynamically
  scoreMax: { fontSize: '14px', color: '#378ADD' },
  verdict: { display: 'inline-block', padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: '500', marginBottom: '12px' },
  metrics: { borderTop: '0.5px solid #E6F1FB', paddingTop: '10px' },
  metricRow: { display: 'flex', justifyContent: 'space-between', marginBottom: '4px' },
  metricLabel: { fontSize: '11px', color: '#378ADD' },
  metricValue: { fontSize: '11px', color: '#042C53', fontWeight: '500' },
};

export default DailyForecast;