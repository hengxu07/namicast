import { getScoreGradient, getScoreColor } from '../utils/scoreColor';

export default function WeeklyForecast({ daily, convert }) {
  if (!daily?.length) return null;

  return (
    <div>
      <div className="text-white font-medium text-sm mb-3">5-Day Forecast</div>
      <div className="grid grid-cols-5 gap-2">
        {daily.map((day, i) => {
          const scoreColor = getScoreGradient(day.score);
          const { bg, text } = getScoreColor(day.score);
          return (
            <div
              key={i}
              className="glass rounded-xl p-3"
              style={{ borderTop: `3px solid ${scoreColor}` }}
            >
              <div className="text-white text-xs font-medium mb-0.5">{i === 0 ? 'Today' : day.weekday}</div>
              <div className="text-slate-500 text-[10px] mb-2">{day.date.slice(5)}</div>

              <div className="text-2xl font-bold leading-none mb-1" style={{ color: scoreColor }}>
                {day.score}
              </div>
              <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-medium mb-2"
                    style={{ background: bg, color: text }}>
                {day.verdict}
              </span>

              <div className="border-t border-white/5 pt-2 space-y-1">
                {[
                  { label: 'Waves',  value: convert.height(day.waveHeight) },
                  { label: 'Wind',   value: `${convert.speed(day.windSpeed)} ${day.windDirection}` },
                  { label: 'Period', value: `${day.wavePeriod}s` },
                ].map(({ label, value }) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-slate-500 text-[10px]">{label}</span>
                    <span className="text-slate-200 text-[10px] font-medium">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
