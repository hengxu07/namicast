import { useState } from 'react';

const BOARDS = ['Longboard', 'Shortboard', 'Funboard'];
const SKILLS = ['Beginner', 'Beg-Intermediate', 'Intermediate', 'Advanced'];

export function loadProfile() {
  try { return JSON.parse(localStorage.getItem('namicast_profile')) || {}; } catch { return {}; }
}

export default function ProfileModal({ onClose, onSave }) {
  const [profile, setProfile] = useState(() => ({
    name: '', board: 'Longboard', skill: 'Beg-Intermediate', ...loadProfile(),
  }));

  const save = () => {
    localStorage.setItem('namicast_profile', JSON.stringify(profile));
    onSave(profile); onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="glass rounded-2xl p-6 w-full max-w-sm shadow-2xl shadow-black/50">
        <div className="text-white font-semibold text-base mb-5">Your surf profile</div>

        <label className="text-slate-500 text-xs uppercase tracking-widest mb-2 block">Name (optional)</label>
        <input
          className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2.5 text-sm text-white placeholder-slate-500 outline-none focus:border-sky-500/50 transition-colors mb-5"
          placeholder="e.g. Heng"
          value={profile.name}
          onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
        />

        <label className="text-slate-500 text-xs uppercase tracking-widest mb-2 block">Board</label>
        <div className="flex flex-wrap gap-2 mb-5">
          {BOARDS.map(b => (
            <button
              key={b}
              onClick={() => setProfile(p => ({ ...p, board: b }))}
              className={`chip ${profile.board === b ? 'chip-active' : 'chip-inactive'}`}
            >{b}</button>
          ))}
        </div>

        <label className="text-slate-500 text-xs uppercase tracking-widest mb-2 block">Skill level</label>
        <div className="flex flex-wrap gap-2 mb-6">
          {SKILLS.map(sk => (
            <button
              key={sk}
              onClick={() => setProfile(p => ({ ...p, skill: sk }))}
              className={`chip ${profile.skill === sk ? 'chip-active' : 'chip-inactive'}`}
            >{sk}</button>
          ))}
        </div>

        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl text-sm text-slate-400 hover:text-white transition-colors"
            style={{ background: 'rgba(255,255,255,0.05)' }}
          >Cancel</button>
          <button
            onClick={save}
            className="flex-1 py-2.5 rounded-xl bg-sky-500 hover:bg-sky-400 text-white text-sm font-medium transition-colors"
          >Save profile</button>
        </div>
      </div>
    </div>
  );
}
