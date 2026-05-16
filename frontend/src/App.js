import { useState, useRef } from 'react';
import axios from 'axios';
import ChatInterface from './components/ChatInterface';
import DailyForecast from './components/DailyForecast';
import WeeklyForecast from './components/WeeklyForecast';
import ProfileModal, { loadProfile } from './components/ProfileModal';
import { getScoreGradient, getScoreColor } from './utils/scoreColor';

const API = process.env.REACT_APP_API_URL;

const SPOTS = [
  { name: 'San Onofre',         lat: 33.37, lng: -117.57 },
  { name: 'Doheny State Beach', lat: 33.46, lng: -117.68 },
  { name: 'Huntington Beach',   lat: 33.66, lng: -118.00 },
  { name: 'Malibu',             lat: 34.04, lng: -118.68 },
  { name: 'Trestles',           lat: 33.38, lng: -117.59 },
  { name: 'Rincon',             lat: 34.37, lng: -119.47 },
];

function App() {
  const [search, setSearch]           = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [board, setBoard]             = useState(() => loadProfile().board || 'Longboard');
  const [skill, setSkill]             = useState(() => loadProfile().skill || 'Beg-Intermediate');
  const [showProfile, setShowProfile] = useState(false);
  const [result, setResult]           = useState(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState('');
  const [selectedSpot, setSelectedSpot] = useState(null);
  const [units, setUnits]             = useState({ height: 'ft', temp: 'F', speed: 'mph' });
  const [showSettings, setShowSettings] = useState(false);

  const { toggle, isFavorite } = useFavorites();
  const searchRef = useRef(null);

  const convert = {
    height: v => units.height === 'ft' ? `${v} ft` : `${(v / 3.28084).toFixed(1)} m`,
    temp:   v => units.temp   === 'F'  ? `${v}°F`  : `${((v-32)*5/9).toFixed(1)}°C`,
    speed:  v => units.speed  === 'mph'? `${v} mph` : `${(v*1.60934).toFixed(1)} km/h`,
  };

  const handleSearch = async () => {
    if (!search.trim()) return;
    setLoading(true); setError('');
    try {
      const res = await axios.get('https://nominatim.openstreetmap.org/search', {
        params: { q: search, format: 'json', limit: 1 },
        headers: { 'Accept-Language': 'en' },
      });
      if (!res.data.length) { setError('Location not found.'); setLoading(false); return; }
      const p = res.data[0];
      await handleCheck({ name: p.display_name.split(',')[0], lat: parseFloat(p.lat), lng: parseFloat(p.lon) });
    } catch { setError('Search failed. Please try again.'); setLoading(false); }
  };

  const handleCheck = async (spot) => {
    setLoading(true); setError(''); setResult(null);
    try {
      const [forecastRes, spotInfoRes, dailyRes] = await Promise.all([
        axios.get(`${API}/forecast`,       { params: { lat: spot.lat, lng: spot.lng, board: board.toLowerCase(), skill: skill.toLowerCase(), spot_name: spot.name } }),
        axios.get(`${API}/spot-info`,      { params: { spot_name: spot.name } }),
        axios.get(`${API}/forecast/daily`, { params: { lat: spot.lat, lng: spot.lng, board: board.toLowerCase(), skill: skill.toLowerCase(), spot_name: spot.name } }),
      ]);
      setResult({ ...forecastRes.data, spotInfo: spotInfoRes.data, daily: dailyRes.data.daily });
      setSelectedSpot(spot);
    } catch { setError('Failed to fetch forecast. Please try again.'); }
    setLoading(false);
  };

  const scoreColor   = result ? getScoreGradient(result.analysis.score) : null;
  const scorePill    = result ? getScoreColor(result.analysis.score) : null;

  return (
    <div className="min-h-screen bg-[#020817] text-white">
      {showProfile && (
        <ProfileModal onClose={() => setShowProfile(false)} onSave={p => { setBoard(p.board); setSkill(p.skill); }} />
      )}

      {/* ── Header ── */}
      <header className="sticky top-0 z-40" style={{ background: 'rgba(7,20,40,0.85)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)', borderBottom: '1px solid rgba(56,189,248,0.1)' }}>
        <div className="max-w-2xl mx-auto flex items-center gap-3 px-4 py-3">
          {/* Logo */}
          <div className="text-lg font-semibold tracking-tight shrink-0">
            <span className="text-slate-500">波</span>{' '}
            <span style={{ background: 'linear-gradient(90deg, #38bdf8, #818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Namicast</span>
          </div>

          {/* Search */}
          <div className="flex-1" ref={searchRef}>
            <div className="flex items-center gap-2 rounded-xl px-3 py-2 glass">
              <input
                className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 outline-none min-w-0"
                placeholder="Search a surf spot..."
                value={search}
                onChange={e => { setSearch(e.target.value); setShowDropdown(true); }}
                onFocus={() => setShowDropdown(true)}
                onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
              />
              <button
                onClick={() => setShowDropdown(d => !d)}
                className="text-slate-500 hover:text-slate-300 text-xs transition-colors shrink-0"
              >▾</button>
              <button
                onClick={handleSearch}
                className="px-3 py-1 text-white text-xs font-medium rounded-lg shrink-0 transition-opacity hover:opacity-90"
              style={{ background: 'linear-gradient(135deg, #38bdf8, #818cf8)' }}
              >Search</button>
            </div>
          </div>

          {/* Icons */}
          <button onClick={() => setShowProfile(true)}    className="p-2 rounded-lg glass glass-hover text-slate-400 hover:text-white text-sm transition-colors shrink-0">👤</button>
          <button onClick={() => setShowSettings(s => !s)} className="p-2 rounded-lg glass glass-hover text-slate-400 hover:text-white text-sm transition-colors shrink-0">⚙️</button>
        </div>
      </header>

      {/* Invisible overlay — catches clicks outside the dropdown */}
      {showDropdown && (
        <div className="fixed inset-0" style={{ zIndex: 9998 }} onClick={() => setShowDropdown(false)} />
      )}

      {/* Dropdown — rendered outside header to escape its stacking context */}
      {showDropdown && (() => {
        const rect = searchRef.current?.getBoundingClientRect();
        if (!rect) return null;
        const filtered = SPOTS.filter(s => s.name.toLowerCase().includes(search.toLowerCase()));
        if (!filtered.length) return null;
        return (
          <div
            className="rounded-xl overflow-hidden shadow-2xl shadow-black/60"
            style={{
              position: 'fixed',
              top: rect.bottom + 6,
              left: rect.left,
              width: rect.width,
              zIndex: 9999,
              background: 'rgba(7,20,40,0.97)',
              border: '1px solid rgba(56,189,248,0.15)',
              backdropFilter: 'blur(16px)',
              WebkitBackdropFilter: 'blur(16px)',
            }}
          >
            {filtered.map(spot => (
              <button
                key={spot.name}
                onMouseDown={() => { setSearch(spot.name); handleCheck(spot); setShowDropdown(false); }}
                className="w-full text-left px-4 py-2.5 text-sm text-slate-300 hover:bg-white/10 hover:text-white transition-colors"
              >
                🏄 {spot.name}
              </button>
            ))}
          </div>
        );
      })()}

      <main className="max-w-2xl mx-auto px-4 py-6 space-y-4">

        {/* ── Settings Panel ── */}
        {showSettings && (
          <div className="glass rounded-2xl p-4 space-y-3">
            {[
              { label: 'Wave height', key: 'height', opts: ['ft', 'm'] },
              { label: 'Temperature', key: 'temp',   opts: ['F', 'C'] },
              { label: 'Wind speed',  key: 'speed',  opts: ['mph', 'km/h', 'm/s'] },
            ].map(({ label, key, opts }) => (
              <div key={key} className="flex items-center justify-between">
                <span className="text-slate-400 text-sm">{label}</span>
                <div className="flex gap-1">
                  {opts.map(u => (
                    <button
                      key={u}
                      onClick={() => setUnits(prev => ({ ...prev, [key]: u }))}
                      className={`chip ${units[key] === u ? 'chip-active' : 'chip-inactive'}`}
                    >{u}</button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Chat ── */}
        <ChatInterface board={board} skill={skill} />

        {/* ── Error / Loading ── */}
        {error && <p className="text-red-400 text-sm">{error}</p>}
        {loading && (
          <div className="glass rounded-2xl p-8 text-center">
            <p className="text-sky-400 text-sm animate-pulse">🌊 Checking conditions...</p>
          </div>
        )}

        {/* ── Results ── */}
        {result && !loading && (
          <>
            {/* Score card */}
            <div className="glass rounded-2xl p-6">
              {/* Spot tags */}
              {result.spotInfo && (
                <div className="flex flex-wrap gap-2 mb-5">
                  <span className="px-2.5 py-1 bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs rounded-full">🏄 {result.spotInfo.type}</span>
                  <span className="px-2.5 py-1 bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs rounded-full">📅 {result.spotInfo.best_season}</span>
                  <span className="px-2.5 py-1 bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs rounded-full">🎯 {result.spotInfo.difficulty}</span>
                  <span className="px-2.5 py-1 bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs rounded-full">⚠️ {result.spotInfo.hazards}</span>
                </div>
              )}

              {/* Favorite + score row */}
              <div className="flex items-start justify-between mb-5">
                <div>
                  <div className="text-7xl font-bold leading-none" style={{ color: scoreColor }}>
                    {result.analysis.score}
                  </div>
                  <div className="text-slate-500 text-xs mt-1">out of 10</div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <span className="px-4 py-1.5 rounded-full text-sm font-medium" style={{ background: scorePill?.bg, color: scorePill?.text }}>
                    {result.analysis.verdict}
                  </span>
                  {selectedSpot && (
                    <button
                      onClick={() => toggle(selectedSpot)}
                      className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                        isFavorite(selectedSpot.name)
                          ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                          : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
                      }`}
                    >
                      {isFavorite(selectedSpot.name) ? '⭐ Saved' : '☆ Save'}
                    </button>
                  )}
                </div>
              </div>

              <p className="text-slate-300 text-sm leading-relaxed mb-4">{result.analysis.summary}</p>

              {/* Analysis tags */}
              <div className="space-y-2 mb-5">
                {result.analysis.wind_analysis && (
                  <div className="text-sm text-slate-300 px-3 py-2.5 rounded-xl" style={{ background: 'rgba(56,189,248,0.05)' }}>
                    💨 {result.analysis.wind_analysis}
                  </div>
                )}
                {result.analysis.spot_analysis && (
                  <div className="text-sm text-slate-300 px-3 py-2.5 rounded-xl" style={{ background: 'rgba(56,189,248,0.05)' }}>
                    🌊 {result.analysis.spot_analysis}
                  </div>
                )}
              </div>

              {/* Metrics grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
                {[
                  { label: 'Wave height', value: convert.height(result.conditions.waveHeight) },
                  { label: 'Period',      value: `${result.conditions.wavePeriod}s` },
                  { label: 'Wind',        value: `${convert.speed(result.conditions.windSpeed)} ${result.conditions.windDirection}` },
                  { label: 'Water temp',  value: convert.temp(result.conditions.waterTemp) },
                  ...(result.conditions.tideHeight !== undefined ? [{ label: 'Tide', value: `${result.conditions.tideHeight}m` }] : []),
                ].map(({ label, value }) => (
                  <div key={label} className="metric-tile">
                    <div className="section-label">{label}</div>
                    <div className="text-white font-semibold text-base">{value}</div>
                  </div>
                ))}
              </div>

              {/* Swells */}
              {result.conditions.swells?.length > 0 && (
                <div className="mb-5 pt-4 border-t border-white/5">
                  <div className="text-slate-400 text-xs uppercase tracking-widest mb-3">Swell breakdown</div>
                  <div className="space-y-2">
                    {result.conditions.swells.map((swell, i) => (
                      <div key={i} className="flex justify-between items-center py-1.5 border-b border-white/5 last:border-0">
                        <span className="text-sky-400 text-xs font-medium">{swell.type}</span>
                        <span className="text-white text-sm font-medium">{convert.height(swell.height)} @ {swell.period}s {swell.direction}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Tags */}
              <div className="flex flex-wrap gap-2">
                <span className="px-3 py-1.5 bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs rounded-lg">🩱 {result.analysis.wetsuit}</span>
                <span className="px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs rounded-lg">⏰ {result.analysis.best_time}</span>
              </div>
            </div>

            {/* Tips */}
            <div className="glass rounded-2xl p-5">
              <div className="text-white font-medium text-sm mb-3">Tips for your session</div>
              <div className="space-y-2.5">
                {(result.analysis.tips || []).map((tip, i) => (
                  <div key={i} className="flex gap-3 text-slate-300 text-sm leading-relaxed">
                    <span className="w-1.5 h-1.5 rounded-full bg-sky-400 mt-2 shrink-0" />
                    {tip}
                  </div>
                ))}
              </div>
            </div>

            {/* 5-Day Forecast */}
            {result.daily && <WeeklyForecast daily={result.daily} convert={convert} />}

            {/* Today's sessions */}
            {result.forecast && <DailyForecast forecasts={result.forecast} convert={convert} />}

            {/* About spot */}
            {result.spotInfo && (
              <div className="glass rounded-2xl p-5">
                <div className="text-white font-medium text-sm mb-2">About {selectedSpot?.name}</div>
                <p className="text-slate-400 text-sm leading-relaxed mb-4">{result.spotInfo.description}</p>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: 'Best swell', value: result.spotInfo.best_swell },
                    { label: 'Best wind',  value: result.spotInfo.best_wind },
                    { label: 'Best tide',  value: result.spotInfo.best_tide },
                    { label: 'Known for',  value: result.spotInfo.known_for },
                  ].map(({ label, value }) => (
                    <div key={label} className="metric-tile">
                      <div className="section-label">{label}</div>
                      <div className="text-slate-200 text-sm font-medium">{value}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function useFavorites() {
  const [favorites, setFavorites] = useState(() => {
    try { return JSON.parse(localStorage.getItem('namicast_favorites')) || []; } catch { return []; }
  });
  const toggle = (spot) => {
    setFavorites(prev => {
      const updated = prev.some(s => s.name === spot.name)
        ? prev.filter(s => s.name !== spot.name)
        : [...prev, spot];
      localStorage.setItem('namicast_favorites', JSON.stringify(updated));
      return updated;
    });
  };
  return { toggle, isFavorite: name => favorites.some(s => s.name === name) };
}

export default App;
