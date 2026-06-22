from pathlib import Path
ROOT = Path(r"D:\codex\tempgmail")

(ROOT / "apps/web/src/lib/api.ts").write_text("""const API = import.meta.env.VITE_API_URL ?? "";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    credentials: "include",
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

export type MailboxResp = { address: string; expiresAt: number; aliasKey?: string; mode: "domain" | "gmail" };
export type Msg = {
  id: string;
  from: string;
  subject: string;
  text: string;
  html: string;
  receivedAt: number;
  read: boolean;
  attachments?: { id: string; key: string; name: string; type: string }[];
};
export type Me = { user: { id: string; email: string; premiumUntil: number | null } | null };

export function mailboxKey(m: { address: string; aliasKey?: string; mode: string }) {
  return m.mode === "gmail" && m.aliasKey ? m.aliasKey : m.address;
}
""", encoding="utf-8")

(ROOT / "apps/web/src/components/Toolbar.tsx").write_text("""import QRCode from "qrcode";
import { useEffect, useState } from "react";
import type { MailboxResp } from "../lib/api";
import { api } from "../lib/api";

type Props = {
  mailbox: MailboxResp;
  mailboxKey: string;
  onDeleted: () => void;
};

export function Toolbar({ mailbox, mailboxKey, onDeleted }: Props) {
  const [qr, setQr] = useState("");
  const [fwd, setFwd] = useState("");
  const base = mailbox.mode === "gmail" ? "/api/gmail-mailbox" : "/api/mailbox";

  useEffect(() => {
    QRCode.toDataURL(mailbox.address, { width: 120, margin: 1 }).then(setQr);
  }, [mailbox.address]);

  const copy = async () => {
    await navigator.clipboard.writeText(mailbox.address);
  };

  const del = async () => {
    await api(`${base}/${encodeURIComponent(mailboxKey)}`, { method: "DELETE" });
    onDeleted();
  };

  const saveFwd = async () => {
    await api(`${base}/${encodeURIComponent(mailboxKey)}/forward`, {
      method: "POST",
      body: JSON.stringify({ forwardTo: fwd || null }),
    });
  };

  return (
    <div className="toolbar">
      <button type="button" onClick={copy}>Copy</button>
      <button type="button" onClick={del}>Delete</button>
      {qr && <img src={qr} alt="QR" className="qr" />}
      <label className="fwd">
        Forward to
        <input value={fwd} onChange={(e) => setFwd(e.target.value)} placeholder="you@example.com" />
        <button type="button" onClick={saveFwd}>Save</button>
      </label>
    </div>
  );
}
""", encoding="utf-8")

print("web partial ok")
