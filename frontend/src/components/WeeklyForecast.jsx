import { getScoreGradient, getScoreColor } from '../utils/scoreColor';

function WeeklyForecast({ daily, convert }) {
    if (!daily || daily.length === 0) return null;

    return (
        <div style={s.container}>
            <div style={s.title}>5-Day Forecast</div>
            <div style={s.grid}>
                {daily.map((day, i) => {
                    const gradientColor = getScoreGradient(day.score); // Smooth interpolated color
                    const { bg, text } = getScoreColor(day.score);     // Verdict pill background
                    return (
                        <div key={i} style={{
                            ...s.card,
                            borderTop: `3px solid ${gradientColor}`,   // Replaces the 3-step version
                        }}>
                            <div style={s.weekday}>{i === 0 ? 'Today' : day.weekday}</div>
                            <div style={s.date}>{day.date.slice(5)}</div>

                            {/* Score number uses smooth gradient color */}
                            <div style={{ ...s.score, color: gradientColor }}>{day.score}</div>

                            {/* Verdict pill uses getScoreColor for background */}
                            <div style={{ ...s.verdict, background: bg, color: text }}>
                                {day.verdict}
                            </div>
                            <div style={s.divider} />
                            <div style={s.metricRow}>
                                <span style={s.metricLabel}>Waves</span>
                                <span style={s.metricValue}>{convert.height(day.waveHeight)}</span>
                            </div>
                            <div style={s.metricRow}>
                                <span style={s.metricLabel}>Wind</span>
                                <span style={s.metricValue}>{convert.speed(day.windSpeed)} {day.windDirection}</span>
                            </div>
                            <div style={s.metricRow}>
                                <span style={s.metricLabel}>Period</span>
                                <span style={s.metricValue}>{day.wavePeriod}s</span>
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
    grid: { display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '8px', overflowX: 'auto' },
    card: { background: '#fff', borderRadius: '12px', padding: '14px 12px', border: '0.5px solid #B5D4F4' },
    weekday: { fontSize: '13px', fontWeight: '500', color: '#042C53', marginBottom: '2px' },
    date: { fontSize: '11px', color: '#378ADD', marginBottom: '10px' },
    score: { fontSize: '32px', fontWeight: '500', lineHeight: '1', marginBottom: '6px' }, // color removed — set dynamically
    verdict: { display: 'inline-block', padding: '2px 8px', borderRadius: '20px', fontSize: '11px', fontWeight: '500', marginBottom: '10px' },
    divider: { height: '0.5px', background: '#E6F1FB', marginBottom: '8px' },
    metricRow: { display: 'flex', justifyContent: 'space-between', marginBottom: '4px' },
    metricLabel: { fontSize: '11px', color: '#378ADD' },
    metricValue: { fontSize: '11px', color: '#042C53', fontWeight: '500' },
};

export default WeeklyForecast;