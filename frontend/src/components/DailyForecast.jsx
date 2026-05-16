import { getScoreGradient, getScoreColor } from '../utils/scoreColor';

const SESSION_ICONS = { 'Dawn patrol': '🌅', 'Morning': '☀️', 'Afternoon': '🌤', 'Evening': '🌇' };

export default function DailyForecast({ forecasts, convert }) {
  if (!forecasts?.length) return null;

  return (
    <div>
      <div className="text-white font-medium text-sm mb-3">Today's sessions</div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {forecasts.map((session, i) => {
          const scoreColor = getScoreGradient(session.score);
          const { bg, text } = getScoreColor(session.score);
          return (
            <div
              key={i}
              className="glass rounded-xl p-4 relative overflow-hidden"
              style={{ borderLeft: `3px solid ${scoreColor}` }}
            >
              {session.best && (
                <div className="absolute -top-px left-1/2 -translate-x-1/2 bg-sky-500 text-white text-[10px] font-medium px-2.5 py-0.5 rounded-b-lg">
                  Best
                </div>
              )}
              <div className="text-white text-xs font-medium mb-0.5">
                {SESSION_ICONS[session.name] || '🌊'} {session.name}
              </div>
              <div className="text-slate-500 text-[10px] mb-3">{session.time}</div>

              <div className="text-3xl font-bold leading-none mb-1.5" style={{ color: scoreColor }}>
                {session.score}<span className="text-sm font-normal text-slate-500">/10</span>
              </div>
              <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-medium mb-3"
                    style={{ background: bg, color: text }}>
                {session.verdict}
              </span>

              <div className="border-t border-white/5 pt-2.5 space-y-1.5">
                {[
                  { label: 'Waves',  value: convert.height(session.waveHeight) },
                  { label: 'Wind',   value: `${convert.speed(session.windSpeed)} ${session.windDirection}` },
                  { label: 'Period', value: `${session.wavePeriod}s` },
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
