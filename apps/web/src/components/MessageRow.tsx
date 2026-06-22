import { useState } from "react";
import type { Msg } from "../lib/api";

function attachmentUrl(key: string) {
  const base = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
  return `${base}/api/attachments/${encodeURIComponent(key)}`;
}

export function MessageRow({ msg, onOpen }: { msg: Msg; onOpen: () => void }) {
  const [open, setOpen] = useState(false);
  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && !msg.read) onOpen();
  };
  return (
    <article className="msg">
      <button type="button" className="msg-head" onClick={toggle}>
        <span className="from">{msg.from}</span>
        <span className="subj">{msg.subject}</span>
        <time>{new Date(msg.receivedAt).toLocaleString()}</time>
      </button>
      {open && (
        <div className="msg-body">
          {msg.html ? <iframe sandbox="" srcDoc={msg.html} title="email-body" className="iframe" /> : <pre>{msg.text}</pre>}
          {(msg.attachments ?? []).map((a) => (
            <a key={a.id} href={attachmentUrl(a.key)} target="_blank" rel="noreferrer">{a.name}</a>
          ))}
        </div>
      )}
    </article>
  );
}
