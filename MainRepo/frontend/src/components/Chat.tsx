import { useEffect, useRef, useState } from "react";
import type { ChatMsg } from "../types";
import { SOURCE_LABEL } from "../format";
import type { Source } from "../types";

const SPARK = <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path fill="#fff" d="M12 2l1.8 5.6L19 9.5l-5.2 1.9L12 17l-1.8-5.6L5 9.5l5.2-1.9zM19 14l.9 2.6 2.6.9-2.6.9L19 21l-.9-2.6-2.6-.9 2.6-.9z" /></svg>;
const SEND = <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path d="M12 19V5M5 12l7-7 7 7" stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>;

export function ChatBar({ onOpen }: { onOpen: () => void }) {
  return (
    <button className="chat-bar" onClick={onOpen} aria-label="Ask about your outage">
      <span className="spark">{SPARK}</span>
      <span className="chat-bar-text"><b>Ask about your outage</b><small>AI assistant</small></span>
      <span className="send-ghost">{SEND}</span>
    </button>
  );
}

export function ChatSheet({ context, suggestions, messages, busy, onSend, onClose }: {
  context: string; suggestions: string[]; messages: ChatMsg[]; busy: boolean;
  onSend: (text: string) => void; onClose: () => void;
}) {
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [messages, busy]);
  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const send = (s: string) => { const v = s.trim(); if (!v || busy) return; onSend(v); setText(""); };
  return (
    <div className="chat-layer" role="dialog" aria-modal="true" aria-label="Outage assistant">
      <div className="sheet-backdrop" onClick={onClose} />
      <div className="chat-sheet">
        <div className="sheet-grabber" aria-hidden />
        <div className="chat-head">
          <span className="spark">{SPARK}</span>
          <div><b>Outage assistant</b><small>AI assistant</small></div>
          <button className="icon-btn" onClick={onClose} aria-label="Minimize chat">
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" /></svg>
          </button>
        </div>
        <div className="ctx-chip"><span className="dot" />{context}</div>
        <div className="chat-scroll" aria-live="polite">
          {messages.map((m, i) => (
            <div key={i} className={`bubble-row ${m.role}`}>
              <div className={`bubble ${m.role}${m.safety_flag ? " safety" : ""}`}>
                {m.safety_flag && <div><span className="safety-label">SAFETY</span></div>}
                {m.content}
                {m.role === "assistant" && m.source && (
                  <div className="bubble-src">{SOURCE_LABEL[m.source as Source] ?? m.source}</div>
                )}
              </div>
            </div>
          ))}
          {busy && <div className="bubble-row assistant"><div className="bubble assistant typing" aria-label="Assistant is typing"><span /><span /><span /></div></div>}
          {!busy && (
            <div className="suggest">
              {suggestions.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
            </div>
          )}
          <div ref={end} />
        </div>
        <p className="disclaimer">AI can make mistakes. Only the utility confirms restoration. In an emergency, call 911.</p>
        <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <input ref={input} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about your outage" maxLength={1000} aria-label="Message" />
          <button type="submit" className="send" aria-label="Send" disabled={busy || !text.trim()}>{SEND}</button>
        </form>
      </div>
    </div>
  );
}
