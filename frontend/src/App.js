import { useState, useEffect } from 'react';
import axios from 'axios';
import DailyForecast from './components/DailyForecast';
import WeeklyForecast from './components/WeeklyForecast';
import { getScoreGradient } from './utils/scoreColor';

const API = process.env.REACT_APP_API_URL;

const SPOTS = [
  { name: 'San Onofre', lat: 33.37, lng: -117.57 },
  { name: 'Huntington Beach', lat: 33.66, lng: -118.00 },
  { name: 'Malibu', lat: 34.04, lng: -118.68 },
  { name: 'Trestles', lat: 33.38, lng: -117.59 },
  { name: 'Rincon', lat: 34.37, lng: -119.47 },
];

const BOARDS = ['Longboard', 'Shortboard', 'Funboard'];
const SKILLS = ['Beginner', 'Intermediate', 'Advanced'];

const verdictColors = {
  Excellent: { bg: '#EAF3DE', color: '#3B6D11' },
  Good: { bg: '#E1F5EE', color: '#0F6E56' },
  Fair: { bg: '#FAEEDA', color: '#854F0B' },
  Poor: { bg: '#FCEBEB', color: '#A32D2D' },
};

function App() {
  const [search, setSearch] = useState('');
  const [board, setBoard] = useState('Longboard');
  const [skill, setSkill] = useState('Intermediate');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selectedSpot, setSelectedSpot] = useState(null);

  const [units, setUnits] = useState({ height: 'ft', temp: 'F', speed: 'mph' });
  const [showSettings, setShowSettings] = useState(false);

  const isMobile = useIsMobile();
  const { favorites, toggle, isFavorite } = useFavorites();

  const s = {
    app: { background: '#E6F1FB', minHeight: '100vh', padding: isMobile ? '16px 12px' : '24px', fontFamily: 'sans-serif' },
    analysisTag: { fontSize: '13px', color: '#185FA5', background: '#E6F1FB', padding: '8px 12px', borderRadius: '8px', marginBottom: '8px', lineHeight: '1.5' },

    // Header stacks vertically on mobile
    header: { display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center', gap: '12px', marginBottom: '16px' },
    logo: { fontSize: '22px', fontWeight: '500', color: '#042C53', whiteSpace: 'nowrap' },
    logoBlue: { color: '#378ADD' },

    // Search bar takes full width on mobile
    searchBar: { flex: 1, maxWidth: isMobile ? '100%' : '400px', background: '#fff', borderRadius: '12px', padding: '8px 14px', border: '0.5px solid #B5D4F4', display: 'flex', alignItems: 'center', gap: '8px' },
    searchBtn: { padding: '6px 14px', background: '#378ADD', color: '#fff', border: 'none', borderRadius: '8px', fontSize: '13px', cursor: 'pointer', whiteSpace: 'nowrap' },
    searchInput: { border: 'none', outline: 'none', fontSize: '14px', color: '#042C53', width: '100%', background: 'transparent' },

    // Settings button aligns right on mobile
    settingsBtn: { padding: '8px', borderRadius: '8px', border: '0.5px solid #B5D4F4', background: '#fff', cursor: 'pointer', fontSize: '16px', alignSelf: isMobile ? 'flex-end' : 'auto' },

    selectors: { display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap', alignItems: 'center' },
    selector: { padding: '6px 14px', borderRadius: '20px', fontSize: '12px', border: '0.5px solid #B5D4F4', background: '#fff', cursor: 'pointer', color: '#185FA5' },
    selectorActive: { background: '#378ADD', color: '#fff', borderColor: '#378ADD' },
    divider: { width: '1px', height: '20px', background: '#B5D4F4' },

    spotList: { display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '20px' },
    spotBtn: { padding: '8px 16px', borderRadius: '10px', border: '0.5px solid #B5D4F4', background: '#fff', cursor: 'pointer', fontSize: '13px', color: '#185FA5' },
    spotBtnActive: { background: '#378ADD', color: '#fff', borderColor: '#378ADD' },

    settingsPanel: { background: '#fff', borderRadius: '12px', padding: '16px', marginBottom: '16px', border: '0.5px solid #B5D4F4' },
    settingsRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' },
    settingsLabel: { fontSize: '13px', color: '#185FA5' },
    settingsBtns: { display: 'flex', gap: '6px' },
    unitBtn: { padding: '4px 10px', borderRadius: '6px', border: '0.5px solid #B5D4F4', background: '#fff', cursor: 'pointer', fontSize: '12px', color: '#185FA5' },
    unitBtnActive: { background: '#378ADD', color: '#fff', borderColor: '#378ADD' },

    error: { color: '#A32D2D', fontSize: '13px', marginBottom: '12px' },
    loading: { textAlign: 'center', padding: '40px 0' },

    // Score card tighter padding on mobile
    scoreCard: { background: '#fff', borderRadius: '16px', padding: isMobile ? '16px' : '24px', marginBottom: '16px', border: '0.5px solid #B5D4F4' },
    scoreRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' },
    scoreBig: { fontSize: isMobile ? '40px' : '48px', fontWeight: '500', lineHeight: '1' }, // color set dynamically
    scoreLabel: { fontSize: '13px', color: '#378ADD', marginTop: '4px' },
    verdict: { padding: '6px 16px', borderRadius: '20px', fontSize: '13px', fontWeight: '500' },
    summary: { fontSize: '13px', color: '#185FA5', lineHeight: '1.6', marginBottom: '16px' },

    // Metrics: 2 columns on mobile instead of auto-fit
    metrics: { display: 'grid', gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(auto-fit, minmax(100px, 1fr))', gap: '10px', marginBottom: '16px' },
    metric: { background: '#E6F1FB', borderRadius: '10px', padding: '12px' },
    metricLabel: { fontSize: '11px', color: '#378ADD', marginBottom: '4px' },
    metricValue: { fontSize: '18px', fontWeight: '500', color: '#042C53' },
    metricUnit: { fontSize: '11px', color: '#185FA5' },

    spotInfoBar: { display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px', paddingBottom: '16px', borderBottom: '0.5px solid #E6F1FB' },
    spotInfoItem: { fontSize: '12px', color: '#185FA5', background: '#E6F1FB', padding: '4px 10px', borderRadius: '20px' },

    spotGrid: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginTop: '12px' },
    spotGridItem: { background: '#E6F1FB', borderRadius: '8px', padding: '10px' },
    spotGridValue: { fontSize: '13px', color: '#042C53', fontWeight: '500', marginTop: '4px' },

    spotSection: { marginBottom: '8px' },
    spotSectionLabel: { fontSize: '11px', color: '#378ADD', fontWeight: '500', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' },
    favBtn: { padding: '6px 14px', borderRadius: '20px', fontSize: '12px', fontWeight: '500', cursor: 'pointer', marginBottom: '16px' },

    swellSection: { marginTop: '16px', paddingTop: '16px', borderTop: '0.5px solid #B5D4F4' },
    swellRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '0.5px solid #E6F1FB' },
    swellType: { fontSize: '12px', color: '#378ADD', fontWeight: '500' },
    swellData: { fontSize: '13px', color: '#042C53', fontWeight: '500' },

    tags: { display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '16px' },
    tagBlue: { background: '#E6F1FB', color: '#185FA5', padding: '6px 12px', borderRadius: '8px', fontSize: '12px' },
    tagGreen: { background: '#EAF3DE', color: '#3B6D11', padding: '6px 12px', borderRadius: '8px', fontSize: '12px' },

    // tipsCard gets bottom margin so cards don't stick together
    tipsCard: { background: '#fff', borderRadius: '16px', padding: isMobile ? '16px' : '20px', border: '0.5px solid #B5D4F4', marginBottom: '16px' },
    tipsTitle: { fontSize: '14px', fontWeight: '500', color: '#042C53', marginBottom: '12px' },
    tip: { display: 'flex', gap: '10px', marginBottom: '10px', alignItems: 'flex-start', fontSize: '13px', color: '#185FA5', lineHeight: '1.5' },
    tipDot: { width: '6px', height: '6px', borderRadius: '50%', background: '#378ADD', marginTop: '5px', flexShrink: 0 },
  };

  const convert = {
    height: (val) => units.height === 'ft' ? `${val} ft` : `${(val / 3.28084).toFixed(1)} m`,
    temp: (val) => units.temp === 'F' ? `${val}°F` : `${((val - 32) * 5 / 9).toFixed(1)}°C`,
    speed: (val) => units.speed === 'mph' ? `${val} mph` : `${(val * 1.60934).toFixed(1)} km/h`,
  };

  const handleSearch = async () => {
    if (!search.trim()) return;
    setLoading(true);
    setError('');
    try {
      const res = await axios.get('https://nominatim.openstreetmap.org/search', {
        params: {
          q: search,
          format: 'json',
          limit: 1,
        },
        headers: { 'Accept-Language': 'en' }
      });
      if (res.data.length === 0) {
        setError('Location not found. Try a different search.');
        setLoading(false);
        return;
      }
      const place = res.data[0];
      const spot = {
        name: place.display_name.split(',')[0],
        lat: parseFloat(place.lat),
        lng: parseFloat(place.lon),
      };
      await handleCheck(spot);
    } catch (err) {
      setError('Search failed. Please try again.');
      setLoading(false);
    }
  };

  const handleCheck = async (spot) => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const [forecastRes, spotInfoRes, dailyRes] = await Promise.all([
        axios.get(`${API}/forecast`, {
          params: {
            lat: spot.lat,
            lng: spot.lng,
            board: board.toLowerCase(),
            skill: skill.toLowerCase(),
            spot_name: spot.name,
          }
        }),
        axios.get(`${API}/spot-info`, {
          params: { spot_name: spot.name }
        }),
        axios.get(`${API}/forecast/daily`, {
          params: {
            lat: spot.lat,
            lng: spot.lng,
            board: board.toLowerCase(),
            skill: skill.toLowerCase(),
          }
        })
      ]);
      setResult({
        ...forecastRes.data,
        spotInfo: spotInfoRes.data,
        daily: dailyRes.data.daily,
      });
      setSelectedSpot(spot);
    } catch (err) {
      setError('Failed to fetch forecast. Please try again.');
    }
    setLoading(false);
  };

  const filteredSpots = SPOTS.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={s.app}>
      {/* Header */}
      <div style={s.header}>
        <div style={s.logo}>波 <span style={s.logoBlue}>Namicast</span></div>
        <div style={s.searchBar}>
          <input
            style={s.searchInput}
            placeholder="Search a surf spot..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
          <button style={s.searchBtn} onClick={handleSearch}>Search</button>
        </div>
        <button style={s.settingsBtn} onClick={() => setShowSettings(!showSettings)}>
          ⚙️
        </button>
      </div>

      {/* Selectors */}
      <div style={s.selectors}>
        {BOARDS.map(b => (
          <button
            key={b}
            style={{ ...s.selector, ...(board === b ? s.selectorActive : {}) }}
            onClick={() => setBoard(b)}
          >
            {b}
          </button>
        ))}
        <div style={s.divider} />
        {SKILLS.map(sk => (
          <button
            key={sk}
            style={{ ...s.selector, ...(skill === sk ? s.selectorActive : {}) }}
            onClick={() => setSkill(sk)}
          >
            {sk}
          </button>
        ))}
      </div>

      {/* Favorite spots */}
      {favorites.length > 0 && (
        <div style={s.spotSection}>
          <div style={s.spotSectionLabel}>⭐ Favorites</div>
          <div style={s.spotList}>
            {favorites.map(spot => (
              <button
                key={spot.name}
                style={{ ...s.spotBtn, ...(selectedSpot?.name === spot.name ? s.spotBtnActive : {}) }}
                onClick={() => handleCheck(spot)}
                disabled={loading}
              >
                ⭐ {spot.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Default spots */}
      <div style={s.spotSection}>
        {favorites.length > 0 && <div style={s.spotSectionLabel}>📍 Popular spots</div>}
        <div style={s.spotList}>
          {filteredSpots.map(spot => (
            <button
              key={spot.name}
              style={{ ...s.spotBtn, ...(selectedSpot?.name === spot.name ? s.spotBtnActive : {}) }}
              onClick={() => handleCheck(spot)}
              disabled={loading}
            >
              🏄 {spot.name}
            </button>
          ))}
        </div>
      </div>

      {showSettings && (
        <div style={s.settingsPanel}>
          <div style={s.settingsRow}>
            <span style={s.settingsLabel}>Wave height</span>
            <div style={s.settingsBtns}>
              {['ft', 'm'].map(u => (
                <button
                  key={u}
                  style={{ ...s.unitBtn, ...(units.height === u ? s.unitBtnActive : {}) }}
                  onClick={() => setUnits({ ...units, height: u })}
                >{u}</button>
              ))}
            </div>
          </div>
          <div style={s.settingsRow}>
            <span style={s.settingsLabel}>Temperature</span>
            <div style={s.settingsBtns}>
              {['F', 'C'].map(u => (
                <button
                  key={u}
                  style={{ ...s.unitBtn, ...(units.temp === u ? s.unitBtnActive : {}) }}
                  onClick={() => setUnits({ ...units, temp: u })}
                >°{u}</button>
              ))}
            </div>
          </div>
          <div style={s.settingsRow}>
            <span style={s.settingsLabel}>Wind speed</span>
            <div style={s.settingsBtns}>
              {['mph', 'km/h', 'm/s'].map(u => (
                <button
                  key={u}
                  style={{ ...s.unitBtn, ...(units.speed === u ? s.unitBtnActive : {}) }}
                  onClick={() => setUnits({ ...units, speed: u })}
                >{u}</button>
              ))}
            </div>
          </div>
        </div>
      )}


      {error && <p style={s.error}>{error}</p>}

      {loading && (
        <div style={s.loading}>
          <p style={{ color: '#378ADD', fontSize: '14px' }}>🌊 Checking conditions...</p>
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div>
          {/* Score card */}
          <div style={s.scoreCard}>
            {result.spotInfo && (
              <div style={s.spotInfoBar}>
                <span style={s.spotInfoItem}>🏄 {result.spotInfo.type}</span>
                <span style={s.spotInfoItem}>📅 Best: {result.spotInfo.best_season}</span>
                <span style={s.spotInfoItem}>🎯 {result.spotInfo.difficulty}</span>
                <span style={s.spotInfoItem}>⚠️ {result.spotInfo.hazards}</span>
              </div>
            )}
            {/* Favorite toggle button */}
            {selectedSpot && (
              <button
                style={{
                  ...s.favBtn,
                  background: isFavorite(selectedSpot.name) ? '#FFF8E1' : '#fff',
                  color: isFavorite(selectedSpot.name) ? '#F59E0B' : '#378ADD',
                  border: `0.5px solid ${isFavorite(selectedSpot.name) ? '#F59E0B' : '#B5D4F4'}`,
                }}
                onClick={() => toggle(selectedSpot)}
              >
                {isFavorite(selectedSpot.name) ? '⭐ Saved' : '☆ Save spot'}
              </button>
            )}
            <div style={s.scoreRow}>
              <div>
                <div style={{ ...s.scoreBig, color: getScoreGradient(result.analysis.score) }}>
                  {result.analysis.score}
                </div>
                <div style={s.scoreLabel}>out of 10</div>
              </div>
              <div style={{
                ...s.verdict,
                background: verdictColors[result.analysis.verdict]?.bg || '#f0f0f0',
                color: verdictColors[result.analysis.verdict]?.color || '#333',
              }}>
                {result.analysis.verdict} conditions
              </div>
            </div>

            <p style={s.summary}>{result.analysis.summary}</p>

            {result.analysis.wind_analysis && (
              <div style={s.analysisTag}>
                💨 {result.analysis.wind_analysis}
              </div>
            )}
            {result.analysis.spot_analysis && (
              <div style={s.analysisTag}>
                🌊 {result.analysis.spot_analysis}
              </div>
            )}


            <div style={s.metrics}>
              <div style={s.metric}>
                <div style={s.metricLabel}>Wave height</div>
                <div style={s.metricValue}>{convert.height(result.conditions.waveHeight)}</div>
              </div>
              <div style={s.metric}>
                <div style={s.metricLabel}>Period</div>
                <div style={s.metricValue}>{result.conditions.wavePeriod} <span style={s.metricUnit}>sec</span></div>
              </div>
              <div style={s.metric}>
                <div style={s.metricLabel}>Wind</div>
                <div style={s.metricValue}>{convert.speed(result.conditions.windSpeed)} <span style={s.metricUnit}>{result.conditions.windDirection}</span></div>
              </div>
              <div style={s.metric}>
                <div style={s.metricLabel}>Water temp</div>
                <div style={s.metricValue}>{convert.temp(result.conditions.waterTemp)}</div>
              </div>
              {result.conditions.tideHeight !== undefined && (
                <div style={s.metric}>
                  <div style={s.metricLabel}>Tide</div>
                  <div style={s.metricValue}>{result.conditions.tideHeight} <span style={s.metricUnit}>m</span></div>
                </div>
              )}
            </div>
            {result.conditions.swells && result.conditions.swells.length > 0 && (
              <div style={s.swellSection}>
                <div style={s.tipsTitle}>Swell breakdown</div>
                {result.conditions.swells.map((swell, i) => (
                  <div key={i} style={s.swellRow}>
                    <span style={s.swellType}>{swell.type}</span>
                    <span style={s.swellData}>{convert.height(swell.height)} @ {swell.period}s {swell.direction}</span>
                  </div>
                ))}
              </div>
            )}

            <div style={s.tags}>
              <span style={s.tagBlue}>🩱 {result.analysis.wetsuit}</span>
              <span style={s.tagGreen}>⏰ {result.analysis.best_time}</span>
            </div>
          </div>

          {/* Tips */}
          <div style={s.tipsCard}>
            <div style={s.tipsTitle}>Tips for your session</div>
            {result.analysis.tips.map((tip, i) => (
              <div key={i} style={s.tip}>
                <div style={s.tipDot} />
                {tip}
              </div>
            ))}
          </div>

          {/* 5-Day Forecast */}
          {result.daily && (
            <WeeklyForecast daily={result.daily} convert={convert} />
          )}

          {/* Today's sessions */}
          {result.forecast && (
            <DailyForecast forecasts={result.forecast} convert={convert} />
          )}

          {/* About spot */}
          {result.spotInfo && (
            <div style={s.tipsCard}>
              <div style={s.tipsTitle}>About {selectedSpot?.name}</div>
              <p style={s.summary}>{result.spotInfo.description}</p>
              <div style={s.spotGrid}>
                <div style={s.spotGridItem}>
                  <div style={s.metricLabel}>Best swell</div>
                  <div style={s.spotGridValue}>{result.spotInfo.best_swell}</div>
                </div>
                <div style={s.spotGridItem}>
                  <div style={s.metricLabel}>Best wind</div>
                  <div style={s.spotGridValue}>{result.spotInfo.best_wind}</div>
                </div>
                <div style={s.spotGridItem}>
                  <div style={s.metricLabel}>Best tide</div>
                  <div style={s.spotGridValue}>{result.spotInfo.best_tide}</div>
                </div>
                <div style={s.spotGridItem}>
                  <div style={s.metricLabel}>Known for</div>
                  <div style={s.spotGridValue}>{result.spotInfo.known_for}</div>
                </div>
              </div>
            </div>
          )}

        </div>
      )}
    </div>
  );
}

// Returns true when viewport width is below 600px
function useIsMobile() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 600);
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 600);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);
  return isMobile;
}

// Persists favorite spots to localStorage
function useFavorites() {
  const [favorites, setFavorites] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('namicast_favorites')) || [];
    } catch {
      return [];
    }
  });

  const toggle = (spot) => {
    setFavorites(prev => {
      const exists = prev.some(s => s.name === spot.name);
      const updated = exists
        ? prev.filter(s => s.name !== spot.name)
        : [...prev, { name: spot.name, lat: spot.lat, lng: spot.lng }];
      localStorage.setItem('namicast_favorites', JSON.stringify(updated));
      return updated;
    });
  };

  const isFavorite = (spotName) => favorites.some(s => s.name === spotName);

  return { favorites, toggle, isFavorite };
}

export default App;