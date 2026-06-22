from pathlib import Path

def w(path: str, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

w("apps/api/src/security.ts", """import type { Env } from "./env";

export async function verifyTurnstile(token: string | undefined, ip: string, env: Env): Promise<boolean> {
  if (!env.TURNSTILE_SECRET) return true;
  if (!token) return false;
  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ secret: env.TURNSTILE_SECRET, response: token, remoteip: ip }),
  });
  const data = (await res.json()) as { success?: boolean };
  return Boolean(data.success);
}

export async function allowRate(env: Env, ip: string, limit = 10): Promise<boolean> {
  const key = `rl:${ip}:${Math.floor(Date.now() / 60000)}`;
  const n = Number((await env.RATE_LIMIT.get(key)) ?? "0");
  if (n >= limit) return false;
  await env.RATE_LIMIT.put(key, String(n + 1), { expirationTtl: 120 });
  return true;
}

export function randomLocal(): string {
  return "u" + crypto.randomUUID().replace(/-/g, "").slice(0, 10);
}

export function sessionIdFromRequest(req: Request): string {
  const cookie = req.headers.get("Cookie") ?? "";
  const m = cookie.match(/tm_session=([^;]+)/);
  if (m) return m[1];
  return crypto.randomUUID();
}

export const sessionId = sessionIdFromRequest;
""")

w("apps/api/src/gmail.ts", """import type { Env } from "./env";
import type { InboxMessage } from "@tempgmail/shared";

export interface GmailBackend {
  email: string;
  local: string;
  refreshToken: string;
}

export function parseBackends(env: Env): GmailBackend[] {
  if (!env.GMAIL_BACKENDS_JSON) return [];
  try {
    const raw = JSON.parse(env.GMAIL_BACKENDS_JSON) as Array<{ email: string; refreshToken: string }>;
    return raw.map((b) => ({ email: b.email.toLowerCase(), local: b.email.split("@")[0], refreshToken: b.refreshToken }));
  } catch {
    return [];
  }
}

export function pickBackingGmail(env: Env): GmailBackend | null {
  const list = parseBackends(env);
  if (!list.length) return null;
  return list[Math.floor(Math.random() * list.length)];
}

export function dotify(local: string): string {
  return local.split("").map((ch, i) => (i > 0 && Math.random() < 0.3 ? "." + ch : ch)).join("");
}

export async function getAccessToken(env: Env, refreshToken: string): Promise<string> {
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET,
      refresh_token: refreshToken,
      grant_type: "refresh_token",
    }),
  });
  const data = (await res.json()) as { access_token?: string };
  if (!data.access_token) throw new Error("oauth_failed");
  return data.access_token;
}

export async function lookupRefreshToken(env: Env, accountEmail: string): Promise<string | null> {
  const row = await env.DB.prepare("SELECT refresh_token FROM gmail_accounts WHERE email = ?")
    .bind(accountEmail.toLowerCase())
    .first<{ refresh_token: string }>();
  if (row?.refresh_token) return row.refresh_token;
  const backend = parseBackends(env).find((b) => b.email === accountEmail.toLowerCase());
  return backend?.refreshToken ?? null;
}

function b64url(data: string): string {
  const bytes = new TextEncoder().encode(data);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
}

function decodeBody(payload: { body?: { data?: string }; parts?: unknown[] }, mime: string): string {
  const parts = (payload.parts ?? []) as Array<{ mimeType?: string; body?: { data?: string }; parts?: unknown[] }>;
  for (const p of parts) {
    if (p.mimeType === mime && p.body?.data) return atob(p.body.data.replace(/-/g, "+").replace(/_/g, "/"));
    const nested = decodeBody(p as { body?: { data?: string }; parts?: unknown[] }, mime);
    if (nested) return nested;
  }
  if (payload.body?.data) return atob(payload.body.data.replace(/-/g, "+").replace(/_/g, "/"));
  return "";
}

export function extractPlusTag(to = ""): string | null {
  const m = to.match(/\\+([a-z0-9]+)@gmail\\.com/i);
  return m ? m[1].toLowerCase() : null;
}

export async function fetchGmailMessage(token: string, id: string): Promise<InboxMessage> {
  const raw = await fetch(`https://gmail.googleapis.com/gmail/v1/users/me/messages/${id}?format=full`, {
    headers: { authorization: `Bearer ${token}` },
  }).then((r) => r.json()) as { internalDate?: string; payload?: { headers?: Array<{ name: string; value: string }>; body?: { data?: string }; parts?: unknown[] } };
  const H: Record<string, string> = {};
  for (const h of raw.payload?.headers ?? []) H[h.name.toLowerCase()] = h.value;
  return {
    id,
    from: H["from"] ?? "",
    to: H["to"] ?? H["delivered-to"] ?? "",
    subject: H["subject"] ?? "(no subject)",
    text: decodeBody(raw.payload ?? {}, "text/plain"),
    html: decodeBody(raw.payload ?? {}, "text/html"),
    attachments: [],
    receivedAt: Number(raw.internalDate ?? Date.now()),
    read: false,
  };
}

export async function sendForward(env: Env, token: string, forwardTo: string, msg: InboxMessage): Promise<void> {
  const rawMime = [
    `From: TempMail <${env.OPERATOR_GMAIL || "noreply@tempmail.local"}>`,
    `To: ${forwardTo}`,
    `Reply-To: ${msg.from}`,
    `Subject: [Fwd] ${msg.subject}`,
    "Content-Type: text/html; charset=UTF-8",
    "",
    msg.html || msg.text,
  ].join("\\r\\n");
  await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ raw: b64url(rawMime) }),
  });
}

export async function maybeForwardGmail(env: Env, token: string, aliasKey: string, msg: InboxMessage): Promise<void> {
  const row = await env.DB.prepare("SELECT forward_to FROM gmail_mailboxes WHERE alias_key = ?")
    .bind(aliasKey)
    .first<{ forward_to: string | null }>();
  if (row?.forward_to) await sendForward(env, token, row.forward_to, msg);
}
""")

print("part1 ok")
