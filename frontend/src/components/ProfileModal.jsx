import { useState } from 'react';

const BOARDS = ['Longboard', 'Shortboard', 'Funboard'];
const SKILLS = ['Beginner', 'Beg-Intermediate', 'Intermediate', 'Advanced'];

export function loadProfile() {
  try {
    return JSON.parse(localStorage.getItem('namicast_profile')) || {};
  } catch {
    return {};
  }
}

export default function ProfileModal({ onClose, onSave }) {
  const [profile, setProfile] = useState(() => ({
    name: '',
    board: 'Longboard',
    skill: 'Beg-Intermediate',
    ...loadProfile(),
  }));

  const save = () => {
    localStorage.setItem('namicast_profile', JSON.stringify(profile));
    onSave(profile);
    onClose();
  };

  const s = {
    overlay: { position: 'fixed', inset: 0, background: 'rgba(4,44,83,0.4)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' },
    modal: { background: '#fff', borderRadius: '20px', padding: '24px', width: '100%', maxWidth: '360px', boxShadow: '0 8px 32px rgba(4,44,83,0.15)' },
    title: { fontSize: '16px', fontWeight: '600', color: '#042C53', marginBottom: '20px' },
    label: { fontSize: '12px', color: '#378ADD', fontWeight: '500', marginBottom: '8px', display: 'block' },
    input: { width: '100%', padding: '10px 12px', borderRadius: '10px', border: '0.5px solid #B5D4F4', fontSize: '14px', color: '#042C53', outline: 'none', boxSizing: 'border-box', marginBottom: '16px' },
    group: { display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' },
    chip: { padding: '6px 14px', borderRadius: '20px', fontSize: '12px', border: '0.5px solid #B5D4F4', background: '#fff', cursor: 'pointer', color: '#185FA5' },
    chipActive: { background: '#378ADD', color: '#fff', borderColor: '#378ADD' },
    actions: { display: 'flex', gap: '8px', marginTop: '8px' },
    saveBtn: { flex: 1, padding: '10px', background: '#378ADD', color: '#fff', border: 'none', borderRadius: '10px', fontSize: '14px', fontWeight: '500', cursor: 'pointer' },
    cancelBtn: { padding: '10px 16px', background: '#E6F1FB', color: '#185FA5', border: 'none', borderRadius: '10px', fontSize: '14px', cursor: 'pointer' },
  };

  return (
    <div style={s.overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={s.modal}>
        <div style={s.title}>Your surf profile</div>

        <label style={s.label}>Name (optional)</label>
        <input
          style={s.input}
          placeholder="e.g. Heng"
          value={profile.name}
          onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
        />

        <label style={s.label}>Board</label>
        <div style={s.group}>
          {BOARDS.map(b => (
            <button key={b} style={{ ...s.chip, ...(profile.board === b ? s.chipActive : {}) }} onClick={() => setProfile(p => ({ ...p, board: b }))}>
              {b}
            </button>
          ))}
        </div>

        <label style={s.label}>Skill level</label>
        <div style={s.group}>
          {SKILLS.map(sk => (
            <button key={sk} style={{ ...s.chip, ...(profile.skill === sk ? s.chipActive : {}) }} onClick={() => setProfile(p => ({ ...p, skill: sk }))}>
              {sk}
            </button>
          ))}
        </div>

        <div style={s.actions}>
          <button style={s.cancelBtn} onClick={onClose}>Cancel</button>
          <button style={s.saveBtn} onClick={save}>Save profile</button>
        </div>
      </div>
    </div>
  );
}
