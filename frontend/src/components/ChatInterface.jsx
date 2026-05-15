import { useState, useRef, useEffect } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_API_URL;

export default function ChatInterface({ board, skill }) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Ask me anything — "Is San Ono good for dawn patrol tomorrow?" or "Best spot this weekend for a beginner?"' }
  ]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setLoading(true);

    try {
      const res = await axios.post(`${API}/chat`, {
        message: userMsg,
        board: board.toLowerCase(),
        skill: skill.toLowerCase(),
        history
      });
      setMessages(prev => [...prev, { role: 'assistant', text: res.data.reply }]);
      setHistory(res.data.history);
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', text: 'Something went wrong. Try again.' }]);
    }
    setLoading(false);
  };

  return (
    <div style={{ background: '#fff', borderRadius: '16px', border: '0.5px solid #B5D4F4', marginBottom: '16px', overflow: 'hidden' }}>
      <div style={{ maxHeight: '320px', overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '85%',
            background: m.role === 'user' ? '#378ADD' : '#E6F1FB',
            color: m.role === 'user' ? '#fff' : '#042C53',
            borderRadius: m.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
            padding: '10px 14px',
            fontSize: '13px',
            lineHeight: '1.5',
            whiteSpace: 'pre-wrap'
          }}>
            {m.text}
          </div>
        ))}
        {loading && (
          <div style={{ alignSelf: 'flex-start', background: '#E6F1FB', borderRadius: '12px 12px 12px 2px', padding: '10px 14px', fontSize: '13px', color: '#378ADD' }}>
            🌊 Checking conditions...
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div style={{ display: 'flex', borderTop: '0.5px solid #E6F1FB', padding: '8px' }}>
        <input
          style={{ flex: 1, border: 'none', outline: 'none', fontSize: '14px', padding: '8px', color: '#042C53', background: 'transparent' }}
          placeholder="Ask about any spot, any day..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
        />
        <button
          onClick={send}
          disabled={loading}
          style={{ padding: '8px 16px', background: loading ? '#B5D4F4' : '#378ADD', color: '#fff', border: 'none', borderRadius: '8px', fontSize: '13px', cursor: loading ? 'default' : 'pointer' }}
        >
          Send
        </button>
      </div>
    </div>
  );
}