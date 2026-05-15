import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

const API = process.env.REACT_APP_API_URL;

const SUGGESTIONS = ['San Onofre', 'Doheny State Beach', 'Trestles', 'Malibu', 'Huntington Beach', 'Rincon'];

export default function ChatInterface({ board, skill }) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Ask me anything — "Is San Ono good for dawn patrol tomorrow?" or "Best spot this weekend?"' }
  ]);
  const [toolStatus, setToolStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(() => localStorage.getItem('namicast_session') || null);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const bottomRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, toolStatus]);

  const send = async (text) => {
    const userMsg = (text || input).trim();
    if (!userMsg || loading) return;
    setInput('');
    setLoading(true);
    setToolStatus('');
    setShowSuggestions(false);
    setMessages(prev => [...prev, { role: 'user', text: userMsg }, { role: 'assistant', text: '' }]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg,
          board: board.toLowerCase(),
          skill: skill.toLowerCase(),
          session_id: sessionId,
        }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let event;
          try { event = JSON.parse(line.slice(6)); } catch { continue; }

          if (event.type === 'session') {
            setSessionId(event.session_id);
            localStorage.setItem('namicast_session', event.session_id);
          } else if (event.type === 'text') {
            setMessages(prev => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              updated[updated.length - 1] = { ...last, text: last.text + event.delta };
              return updated;
            });
          } else if (event.type === 'tool_start') {
            setToolStatus(event.label);
          } else if (event.type === 'tool_done') {
            setToolStatus('');
          } else if (event.type === 'error') {
            setMessages(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = { role: 'assistant', text: event.message };
              return updated;
            });
          } else if (event.type === 'done') {
            setLoading(false);
            setToolStatus('');
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: 'assistant', text: 'Something went wrong. Try again.' };
          return updated;
        });
      }
      setLoading(false);
      setToolStatus('');
    }
  };

  const clearSession = () => {
    localStorage.removeItem('namicast_session');
    setSessionId(null);
    setShowSuggestions(true);
    setMessages([{ role: 'assistant', text: 'New session started. Ask me anything!' }]);
  };

  return (
    <div style={{ background: '#fff', borderRadius: '16px', border: '0.5px solid #B5D4F4', marginBottom: '16px', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 16px', borderBottom: '0.5px solid #E6F1FB' }}>
        <span style={{ fontSize: '12px', fontWeight: '600', color: '#042C53' }}>AI Surf Coach</span>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <button onClick={clearSession} style={{ fontSize: '11px', color: '#378ADD', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
            New chat
          </button>
          <button
            onClick={() => setExpanded(e => !e)}
            title={expanded ? 'Collapse' : 'Expand'}
            style={{ fontSize: '14px', color: '#378ADD', background: 'none', border: 'none', cursor: 'pointer', padding: 0, lineHeight: 1 }}
          >
            {expanded ? '⤡' : '⤢'}
          </button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ position: 'relative' }}>
      <div style={{ maxHeight: expanded ? '70vh' : '380px', overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px', transition: 'max-height 0.25s ease' }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '85%',
            background: m.role === 'user' ? '#378ADD' : '#E6F1FB',
            color: m.role === 'user' ? '#fff' : '#042C53',
            borderRadius: m.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
            padding: '10px 14px',
            fontSize: '13px',
            lineHeight: '1.6',
          }}>
            {m.role === 'assistant' ? (
              m.text
                ? <ReactMarkdown
                    components={{
                      p: ({ children }) => <p style={{ margin: '0 0 6px', lineHeight: '1.6' }}>{children}</p>,
                      strong: ({ children }) => <strong style={{ fontWeight: '600', color: '#042C53' }}>{children}</strong>,
                      ul: ({ children }) => <ul style={{ margin: '4px 0', paddingLeft: '18px' }}>{children}</ul>,
                      li: ({ children }) => <li style={{ marginBottom: '2px' }}>{children}</li>,
                      a: ({ children }) => <span>{children}</span>,
                    }}
                  >{m.text}</ReactMarkdown>
                : loading && i === messages.length - 1
                  ? <span style={{ opacity: 0.5 }}>▍</span>
                  : null
            ) : (
              m.text
            )}
          </div>
        ))}

        {toolStatus && (
          <div style={{ alignSelf: 'flex-start', fontSize: '12px', color: '#378ADD', padding: '4px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ display: 'inline-block', width: '7px', height: '7px', borderRadius: '50%', background: '#378ADD', animation: 'pulse 1s infinite' }} />
            {toolStatus}
          </div>
        )}

        {/* Quick-start suggestions */}
        {showSuggestions && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '4px' }}>
            {SUGGESTIONS.map(spot => (
              <button
                key={spot}
                onClick={() => send(`Is ${spot} good this weekend?`)}
                style={{ padding: '5px 12px', borderRadius: '20px', border: '0.5px solid #B5D4F4', background: '#F4F9FF', color: '#185FA5', fontSize: '12px', cursor: 'pointer' }}
              >
                🏄 {spot}
              </button>
            ))}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
      {/* Fade gradient — signals more content below */}
      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '48px', background: 'linear-gradient(to bottom, transparent, #fff)', pointerEvents: 'none', borderRadius: '0 0 4px 4px' }} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', borderTop: '0.5px solid #E6F1FB', padding: '8px', gap: '8px' }}>
        <input
          style={{ flex: 1, border: 'none', outline: 'none', fontSize: '14px', padding: '8px', color: '#042C53', background: 'transparent' }}
          placeholder="Ask about any spot, any day..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          disabled={loading}
        />
        <button
          onClick={() => send()}
          disabled={loading}
          style={{ padding: '8px 16px', background: loading ? '#B5D4F4' : '#378ADD', color: '#fff', border: 'none', borderRadius: '8px', fontSize: '13px', cursor: loading ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
        >
          {loading ? '...' : 'Send'}
        </button>
      </div>

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>
    </div>
  );
}
