const API = import.meta.env.VITE_API_URL ?? "";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    credentials: "include",
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

export type MailboxResp = {
  address: string;
  expiresAt: number;
  aliasKey?: string;
  mailboxKey?: string;
  mode: "domain" | "gmail";
};
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

export function mailboxKey(m: { address: string; aliasKey?: string; mailboxKey?: string; mode: string }) {
  return m.mailboxKey ?? (m.mode === "gmail" && m.aliasKey ? m.aliasKey : m.address);
}
