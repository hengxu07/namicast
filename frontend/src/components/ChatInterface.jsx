import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

const API = process.env.REACT_APP_API_URL;

const SUGGESTIONS = ['San Onofre', 'Doheny State Beach', 'Trestles', 'Malibu', 'Huntington Beach', 'Rincon'];

export default function ChatInterface({ board, skill }) {
  const [input, setInput]       = useState('');
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Ask me anything — "Is San Ono good for dawn patrol tomorrow?" or "Best spot this weekend?"' }
  ]);
  const [toolStatus, setToolStatus] = useState('');
  const [loading, setLoading]       = useState(false);
  const [sessionId, setSessionId]   = useState(() => localStorage.getItem('namicast_session') || null);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [expanded, setExpanded]     = useState(false);
  const bottomRef = useRef(null);
  const abortRef  = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, toolStatus]);

  const send = async (text) => {
    const userMsg = (text || input).trim();
    if (!userMsg || loading) return;
    setInput(''); setLoading(true); setToolStatus(''); setShowSuggestions(false);
    setMessages(prev => [...prev, { role: 'user', text: userMsg }, { role: 'assistant', text: '' }]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMsg, board: board.toLowerCase(), skill: skill.toLowerCase(), session_id: sessionId }),
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
            setMessages(prev => { const u = [...prev]; u[u.length-1] = { role: 'assistant', text: event.message }; return u; });
          } else if (event.type === 'done') {
            setLoading(false); setToolStatus('');
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setMessages(prev => { const u = [...prev]; u[u.length-1] = { role: 'assistant', text: 'Something went wrong. Try again.' }; return u; });
      }
      setLoading(false); setToolStatus('');
    }
  };

  const clearSession = () => {
    localStorage.removeItem('namicast_session');
    setSessionId(null); setShowSuggestions(true);
    setMessages([{ role: 'assistant', text: 'New session started. Ask me anything!' }]);
  };

  return (
    <div className="glass rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-sky-400" style={{ boxShadow: '0 0 6px #38bdf8' }} />
          <span className="text-white text-xs font-medium">AI Surf Coach</span>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={clearSession} className="text-slate-500 hover:text-slate-300 text-xs transition-colors">
            New chat
          </button>
          <button
            onClick={() => setExpanded(e => !e)}
            className="text-slate-500 hover:text-slate-300 text-sm transition-colors"
            title={expanded ? 'Collapse' : 'Expand'}
          >
            {expanded ? '⤡' : '⤢'}
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="relative">
        <div
          className="overflow-y-auto px-4 py-4 flex flex-col gap-3 transition-all duration-300"
          style={{ maxHeight: expanded ? '70vh' : '340px' }}
        >
          {messages.map((m, i) => (
            <div
              key={i}
              className={`max-w-[85%] text-sm leading-relaxed px-4 py-2.5 rounded-2xl ${
                m.role === 'user'
                  ? 'self-end bg-sky-500 text-white rounded-br-sm'
                  : 'self-start text-slate-200 rounded-bl-sm'
              }`}
              style={m.role === 'assistant' ? { background: 'rgba(56,189,248,0.07)', border: '1px solid rgba(56,189,248,0.12)' } : {}}
            >
              {m.role === 'assistant' ? (
                m.text
                  ? <ReactMarkdown components={{
                      p:      ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
                      strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
                      ul:     ({ children }) => <ul className="mt-1 ml-4 space-y-0.5 list-disc">{children}</ul>,
                      li:     ({ children }) => <li className="text-slate-300">{children}</li>,
                      a:      ({ children }) => <span>{children}</span>,
                    }}>{m.text}</ReactMarkdown>
                  : loading && i === messages.length - 1
                    ? <span className="text-slate-500">▍</span>
                    : null
              ) : m.text}
            </div>
          ))}

          {toolStatus && (
            <div className="self-start flex items-center gap-2 text-sky-400 text-xs py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse-dot" />
              {toolStatus}
            </div>
          )}

          {/* Suggestions */}
          {showSuggestions && (
            <div className="flex flex-wrap gap-2 mt-1">
              {SUGGESTIONS.map(spot => (
                <button
                  key={spot}
                  onClick={() => send(`Is ${spot} good this weekend?`)}
                  className="px-3 py-1.5 rounded-full text-xs border border-white/10 text-slate-300 hover:bg-white/10 hover:text-white transition-colors"
                  style={{ background: 'rgba(56,189,248,0.05)' }}
                >
                  🏄 {spot}
                </button>
              ))}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Fade gradient */}
        <div className="absolute bottom-0 left-0 right-0 h-10 pointer-events-none rounded-b-2xl"
             style={{ background: 'linear-gradient(to bottom, transparent, #071428)' }} />
      </div>

      {/* Input */}
      <div className="flex gap-2 px-3 py-3 border-t border-white/5">
        <input
          className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 outline-none px-2"
          placeholder="Ask about any spot, any day..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          disabled={loading}
        />
        <button
          onClick={() => send()}
          disabled={loading}
          className={`px-4 py-2 text-white text-xs font-medium rounded-xl transition-colors ${
            loading ? 'bg-sky-500/40 cursor-default' : 'bg-sky-500 hover:bg-sky-400 cursor-pointer'
          }`}
        >
          {loading ? '...' : 'Send'}
        </button>
      </div>
    </div>
  );
}
