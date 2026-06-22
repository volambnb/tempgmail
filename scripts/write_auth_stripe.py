from pathlib import Path
ROOT = Path(r"D:\codex\tempgmail")

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print("w", rel)

w("apps/api/src/auth.ts", r'''import type { Env } from "./env";

const COOKIE = "tm_auth";
const SESSION_MS = 30 * 24 * 60 * 60 * 1000;

export type AuthUser = { id: string; email: string; premiumUntil: number | null };

function b64(bytes: ArrayBuffer): string {
  const u8 = new Uint8Array(bytes);
  let s = "";
  for (const b of u8) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return b64(buf);
}

export async function hashPassword(password: string, secret: string): Promise<string> {
  return sha256(`${secret}:${password}`);
}

export function parseCookies(req: Request): Record<string, string> {
  const out: Record<string, string> = {};
  const raw = req.headers.get("Cookie") ?? "";
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i < 1) continue;
    out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

export function authCookie(sessionId: string, maxAgeSec: number): string {
  return `${COOKIE}=${encodeURIComponent(sessionId)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAgeSec}`;
}

export function clearAuthCookie(): string {
  return `${COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;
}

export async function getUserFromRequest(env: Env, req: Request): Promise<AuthUser | null> {
  const sid = parseCookies(req)[COOKIE];
  if (!sid) return null;
  const row = await env.DB.prepare(
    "SELECT u.id, u.email, u.premium_until FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ? AND s.expires_at > ?",
  )
    .bind(sid, Date.now())
    .first<{ id: string; email: string; premium_until: number | null }>();
  if (!row) return null;
  return { id: row.id, email: row.email, premiumUntil: row.premium_until };
}

export async function createSession(env: Env, userId: string): Promise<string> {
  const id = crypto.randomUUID();
  const exp = Date.now() + SESSION_MS;
  await env.DB.prepare("INSERT INTO sessions (id, user_id, expires_at, created_at) VALUES (?,?,?,?)")
    .bind(id, userId, exp, Date.now())
    .run();
  return id;
}

export async function destroySession(env: Env, req: Request): Promise<void> {
  const sid = parseCookies(req)[COOKIE];
  if (!sid) return;
  await env.DB.prepare("DELETE FROM sessions WHERE id = ?").bind(sid).run();
}

export function isPremium(user: AuthUser | null): boolean {
  return Boolean(user?.premiumUntil && user.premiumUntil > Date.now());
}
''')

w("apps/api/src/stripe.ts", r'''import type { Env } from "./env";

const PREMIUM_MS = 30 * 24 * 60 * 60 * 1000;

export async function createCheckoutSession(env: Env, userId: string, email: string, origin: string): Promise<string | null> {
  if (!env.STRIPE_SECRET_KEY) return null;
  const body = new URLSearchParams({
    mode: "subscription",
    success_url: `${origin}/?premium=1`,
    cancel_url: `${origin}/?premium=0`,
    "line_items[0][price_data][currency]": "usd",
    "line_items[0][price_data][product_data][name]": "TempGmail Premium",
    "line_items[0][price_data][unit_amount]": "499",
    "line_items[0][price_data][recurring][interval]": "month",
    "line_items[0][quantity]": "1",
    customer_email: email,
    "metadata[user_id]": userId,
  });
  const res = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: { authorization: `Bearer ${env.STRIPE_SECRET_KEY}`, "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const data = (await res.json()) as { url?: string };
  return data.url ?? null;
}

export async function handleStripeWebhook(env: Env, req: Request): Promise<Response> {
  if (!env.STRIPE_WEBHOOK_SECRET) return new Response("no webhook secret", { status: 500 });
  const sig = req.headers.get("stripe-signature") ?? "";
  const raw = await req.text();
  let event: { type?: string; data?: { object?: { metadata?: { user_id?: string }; subscription?: string } } };
  try {
    event = JSON.parse(raw);
  } catch {
    return new Response("bad json", { status: 400 });
  }
  if (!sig.includes("t=")) {
    // Dev/local: accept unsigned payload when secret is placeholder
    if (!env.STRIPE_WEBHOOK_SECRET.startsWith("whsec_")) {
      /* continue */
    } else return new Response("missing sig", { status: 400 });
  }
  if (event.type === "checkout.session.completed") {
    const uid = event.data?.object?.metadata?.user_id;
    if (uid) {
      const until = Date.now() + PREMIUM_MS;
      await env.DB.prepare("UPDATE users SET premium_until = ? WHERE id = ?").bind(until, uid).run();
    }
  }
  return new Response(JSON.stringify({ received: true }), { headers: { "content-type": "application/json" } });
}
''')

w("migrations/0002_auth_stripe.sql", r'''ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE mailboxes ADD COLUMN user_id TEXT;
ALTER TABLE gmail_mailboxes ADD COLUMN user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_mailboxes_user ON mailboxes(user_id);
CREATE INDEX IF NOT EXISTS idx_gmail_user ON gmail_mailboxes(user_id);
''')

print("auth stripe migration ok")
