import { Hono } from "hono";
import { cors } from "hono/cors";
import type { Context } from "hono";
import type { Env } from "./env";
import { allowRate, randomLocal, randomReadableTag, sessionIdFromRequest, verifyTurnstile } from "./security";
import { dotify, pickBackingGmail } from "./gmail";
import { getUserFromRequest, isPremium, registerAuthRoutes } from "./auth";
import { registerStripeRoutes } from "./stripe";

const DEFAULT_DOMAIN = "stockai.store";
const TTL_MS = 3600_000;
type AppContext = Context<{ Bindings: Env }>;
const TURNSTILE_SESSION_TTL = 30 * 60;

function sessionCookie(id: string): string {
  return `tm_session=${encodeURIComponent(id)}; Path=/; HttpOnly; SameSite=None; Secure; Max-Age=2592000`;
}

function withSession(c: { header: (n: string, v: string) => void }, sid: string) {
  c.header("Set-Cookie", sessionCookie(sid));
}

async function hasTxtRecord(hostname: string, expected: string): Promise<boolean> {
  const url = `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(hostname)}&type=TXT`;
  const res = await fetch(url, { headers: { accept: "application/dns-json" } });
  if (!res.ok) return false;
  const data = (await res.json()) as { Answer?: Array<{ data?: string }> };
  return (data.Answer ?? []).some((a) => (a.data ?? "").replace(/"/g, "").includes(expected));
}

function normalizeLocalPart(input: unknown): string | null {
  const value = String(input ?? "").toLowerCase().trim();
  if (!value) return null;
  if (value.length > 48) return "";
  if (!/^[a-z0-9._-]+$/.test(value)) return "";
  if (value.startsWith(".") || value.endsWith(".") || value.includes("..")) return "";
  return value;
}

async function recordHistory(
  env: Env,
  sid: string,
  mailboxKey: string,
  display: string,
  kind: "domain" | "gmail",
) {
  await env.DB.prepare(
    "INSERT INTO mailbox_history (id, session_id, mailbox_key, display_address, kind, created_at) VALUES (?,?,?,?,?,?)",
  )
    .bind(crypto.randomUUID(), sid, mailboxKey, display, kind, Date.now())
    .run();
}

export function createApp() {
  const app = new Hono<{ Bindings: Env }>();
  app.use(
    "/api/*",
    cors({
      origin: (origin) => {
        if (!origin) return "";
        const allowed = [
          "https://tempgmail-17a.pages.dev",
          "https://c5542edb.tempgmail-17a.pages.dev",
          "http://127.0.0.1:4173",
          "http://localhost:4173",
          "http://127.0.0.1:5173",
          "http://localhost:5173",
        ];
        if (allowed.includes(origin) || /^https:\/\/[a-z0-9-]+\.tempgmail-17a\.pages\.dev$/.test(origin)) {
          return origin;
        }
        return "";
      },
      credentials: true,
      allowHeaders: ["content-type"],
      allowMethods: ["GET", "POST", "DELETE", "OPTIONS"],
    }),
  );

  async function guard(c: AppContext) {
    const body = await c.req.json().catch(() => ({}));
    const ip = c.req.header("CF-Connecting-IP") ?? "0.0.0.0";
    const token = body.turnstileToken as string | undefined;
    const sid = sessionIdFromRequest(c.req.raw);
    if (c.env.TURNSTILE_SECRET) {
      const verified = await c.env.RATE_LIMIT.get(`ts:${sid}`);
      if (!verified && !(await verifyTurnstile(token, ip, c.env))) {
        return { ok: false as const, res: c.json({ error: "captcha" }, 403) };
      }
    }
    if (!(await allowRate(c.env, ip))) {
      return { ok: false as const, res: c.json({ error: "rate" }, 429) };
    }
    return { ok: true as const, body, ip };
  }

  function mailboxStub(env: Env, key: string) {
    return env.MAILBOX.get(env.MAILBOX.idFromName(key.toLowerCase()));
  }

  async function assertMailboxOwner(c: AppContext, key: string, mode: "domain" | "gmail") {
    const sid = sessionIdFromRequest(c.req.raw);
    const user = await getUserFromRequest(c.env, c.req.raw);
    if (mode === "domain") {
      const row = await c.env.DB.prepare("SELECT session_id, user_id FROM mailboxes WHERE address = ?")
        .bind(key.toLowerCase())
        .first<{ session_id: string | null; user_id: string | null }>();
      if (!row) return false;
      if (user && row.user_id === user.id) return true;
      return row.session_id === sid;
    }
    const row = await c.env.DB.prepare("SELECT session_id, user_id FROM gmail_mailboxes WHERE alias_key = ?")
      .bind(key)
      .first<{ session_id: string | null; user_id: string | null }>();
    if (!row) return false;
    if (user && row.user_id === user.id) return true;
    return row.session_id === sid;
  }

  app.get("/api/config", async (c) => {
    const sid = sessionIdFromRequest(c.req.raw);
    withSession(c, sid);
    return c.json({
      turnstileSiteKey: c.env.TURNSTILE_SITE_KEY || "",
      turnstileVerified: Boolean(await c.env.RATE_LIMIT.get(`ts:${sid}`)),
    });
  });

  app.post("/api/turnstile/verify", async (c) => {
    const { token } = await c.req.json().catch(() => ({ token: "" }));
    const ip = c.req.header("CF-Connecting-IP") ?? "0.0.0.0";
    if (!(await verifyTurnstile(String(token || ""), ip, c.env))) {
      return c.json({ error: "captcha" }, 403);
    }
    const sid = sessionIdFromRequest(c.req.raw);
    await c.env.RATE_LIMIT.put(`ts:${sid}`, "1", { expirationTtl: TURNSTILE_SESSION_TTL });
    withSession(c, sid);
    return c.json({ ok: true });
  });

  app.post("/api/mailbox", async (c) => {
    const g = await guard(c);
    if (!g.ok) return g.res;
    const requestedDomain = String(g.body.domain || "").toLowerCase().trim();
    const requestedLocal = normalizeLocalPart(g.body.local);
    if (requestedLocal === "") return c.json({ error: "invalid_email_id" }, 400);
    const systemDomain = c.env.DEFAULT_DOMAIN || DEFAULT_DOMAIN;
    let domain = systemDomain;
    const expiresAt = Date.now() + TTL_MS;
    const sid = sessionIdFromRequest(c.req.raw);
    const user = await getUserFromRequest(c.env, c.req.raw);
    if (requestedDomain && requestedDomain !== systemDomain) {
      const row = await c.env.DB.prepare("SELECT status FROM domains WHERE hostname = ?")
        .bind(requestedDomain)
        .first<{ status: string }>();
      if (row?.status !== "verified") return c.json({ error: "domain_not_verified" }, 403);
      domain = requestedDomain;
    }
    const address = `${requestedLocal ?? randomLocal()}@${domain}`.toLowerCase();
    const existing = await c.env.DB.prepare("SELECT expires_at FROM mailboxes WHERE address = ?")
      .bind(address)
      .first<{ expires_at: number }>();
    if (existing && existing.expires_at > Date.now() && !requestedLocal) {
      return c.json({ error: "email_id_taken" }, 409);
    }
    if (existing) {
      await mailboxStub(c.env, address).fetch("https://do/delete-all", { method: "POST" });
      await c.env.DB.prepare("DELETE FROM mailboxes WHERE address = ?").bind(address).run();
    }
    try {
      await c.env.DB.prepare(
        "INSERT INTO mailboxes (address, domain, session_id, user_id, expires_at, created_at) VALUES (?,?,?,?,?,?)",
      )
        .bind(address, domain, sid, user?.id ?? null, expiresAt, Date.now())
        .run();
    } catch {
      return c.json({ error: "email_id_taken" }, 409);
    }
    const stub = mailboxStub(c.env, address);
    await stub.fetch("https://do/expire", { method: "POST", body: JSON.stringify({ at: expiresAt }) });
    await recordHistory(c.env, sid, address, address, "domain");
    withSession(c, sid);
    return c.json({ address, expiresAt, mode: "domain" });
  });

  app.post("/api/gmail-mailbox", async (c) => {
    const g = await guard(c);
    if (!g.ok) return g.res;
    const account = pickBackingGmail(c.env);
    if (!account) return c.json({ error: "no_gmail_backend" }, 503);
    const tag = randomReadableTag();
    const display = `${dotify(account.local)}+${tag}@gmail.com`;
    const aliasKey = `${account.email}#${tag}`;
    const expiresAt = Date.now() + TTL_MS;
    const sid = sessionIdFromRequest(c.req.raw);
    const user = await getUserFromRequest(c.env, c.req.raw);
    await c.env.DB.prepare(
      "INSERT INTO gmail_mailboxes (alias_key, display_address, backing_account, plus_tag, session_id, user_id, expires_at, created_at) VALUES (?,?,?,?,?,?,?,?)",
    )
      .bind(aliasKey, display, account.email, tag, sid, user?.id ?? null, expiresAt, Date.now())
      .run();
    const stub = mailboxStub(c.env, aliasKey);
    await stub.fetch("https://do/expire", { method: "POST", body: JSON.stringify({ at: expiresAt }) });
    await stub.fetch("https://do/poll-start", {
      method: "POST",
      body: JSON.stringify({ account: account.email, tag, aliasKey, expiresAt }),
    });
    await recordHistory(c.env, sid, aliasKey, display, "gmail");
    withSession(c, sid);
    return c.json({ address: display, aliasKey, expiresAt, mode: "gmail" });
  });

  app.get("/api/mailbox/:key/messages", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "domain"))) return c.json({ error: "forbidden" }, 403);
    return mailboxStub(c.env, key).fetch("https://do/list");
  });

  app.get("/api/gmail-mailbox/:key/messages", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "gmail"))) return c.json({ error: "forbidden" }, 403);
    return mailboxStub(c.env, key).fetch("https://do/list");
  });

  app.post("/api/mailbox/:key/read", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "domain"))) return c.json({ error: "forbidden" }, 403);
    const { id } = await c.req.json();
    await mailboxStub(c.env, key).fetch("https://do/mark-read", { method: "POST", body: JSON.stringify({ id }) });
    return c.json({ ok: true });
  });

  app.post("/api/gmail-mailbox/:key/read", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "gmail"))) return c.json({ error: "forbidden" }, 403);
    const { id } = await c.req.json();
    await mailboxStub(c.env, key).fetch("https://do/mark-read", { method: "POST", body: JSON.stringify({ id }) });
    return c.json({ ok: true });
  });

  app.delete("/api/mailbox/:key", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "domain"))) return c.json({ error: "forbidden" }, 403);
    await mailboxStub(c.env, key).fetch("https://do/delete-all", { method: "POST" });
    await c.env.DB.prepare("DELETE FROM mailboxes WHERE address = ?").bind(key.toLowerCase()).run();
    return c.json({ ok: true });
  });

  app.delete("/api/gmail-mailbox/:key", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "gmail"))) return c.json({ error: "forbidden" }, 403);
    await mailboxStub(c.env, key).fetch("https://do/delete-all", { method: "POST" });
    await c.env.DB.prepare("DELETE FROM gmail_mailboxes WHERE alias_key = ?").bind(key).run();
    return c.json({ ok: true });
  });

  app.post("/api/mailbox/:key/forward", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "domain"))) return c.json({ error: "forbidden" }, 403);
    const user = await getUserFromRequest(c.env, c.req.raw);
    if (!isPremium(user)) return c.json({ error: "premium_required" }, 402);
    const { forwardTo } = await c.req.json();
    await c.env.DB.prepare("UPDATE mailboxes SET forward_to = ? WHERE address = ?")
      .bind(forwardTo || null, key.toLowerCase())
      .run();
    return c.json({ ok: true });
  });

  app.post("/api/gmail-mailbox/:key/forward", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    if (!(await assertMailboxOwner(c, key, "gmail"))) return c.json({ error: "forbidden" }, 403);
    const user = await getUserFromRequest(c.env, c.req.raw);
    if (!isPremium(user)) return c.json({ error: "premium_required" }, 402);
    const { forwardTo } = await c.req.json();
    await c.env.DB.prepare("UPDATE gmail_mailboxes SET forward_to = ? WHERE alias_key = ?")
      .bind(forwardTo || null, key)
      .run();
    return c.json({ ok: true });
  });

  async function assertAttachmentAccess(c: AppContext, storageKey: string): Promise<boolean> {
    const parts = storageKey.split("/");
    if (parts[0] !== "att" || parts.length < 3) return false;
    const ref = parts[1].toLowerCase();
    const sid = sessionIdFromRequest(c.req.raw);
    const user = await getUserFromRequest(c.env, c.req.raw);
    const domainRow = await c.env.DB.prepare("SELECT session_id, user_id FROM mailboxes WHERE address = ?")
      .bind(ref)
      .first<{ session_id: string | null; user_id: string | null }>();
    if (domainRow) {
      if (user && domainRow.user_id === user.id) return true;
      return domainRow.session_id === sid;
    }
    const gmailRow = await c.env.DB.prepare(
      "SELECT session_id, user_id FROM gmail_mailboxes WHERE display_address = ? OR alias_key = ?",
    )
      .bind(ref, ref)
      .first<{ session_id: string | null; user_id: string | null }>();
    if (!gmailRow) return false;
    if (user && gmailRow.user_id === user.id) return true;
    return gmailRow.session_id === sid;
  }

  app.get("/api/attachments/*", async (c) => {
    const key = decodeURIComponent(c.req.path.replace(/^\/api\/attachments\//, ""));
    if (!(await assertAttachmentAccess(c, key))) return c.json({ error: "forbidden" }, 403);
    const obj = await c.env.ATTACHMENTS.get(key);
    if (!obj) return c.json({ error: "not_found" }, 404);
    const headers = new Headers();
    obj.writeHttpMetadata(headers);
    headers.set("cache-control", "private, max-age=3600");
    headers.set("content-disposition", "inline");
    return new Response(obj.body, { headers });
  });

  app.get("/api/history", async (c) => {
    const sid = sessionIdFromRequest(c.req.raw);
    withSession(c, sid);
    const rows = await c.env.DB.prepare(
      "SELECT mailbox_key, display_address, kind, created_at FROM mailbox_history WHERE session_id = ? ORDER BY created_at DESC LIMIT 30",
    )
      .bind(sid)
      .all<{ mailbox_key: string; display_address: string; kind: string; created_at: number }>();
    const out = [];
    for (const r of rows.results ?? []) {
      if (r.kind === "gmail") {
        const g = await c.env.DB.prepare("SELECT expires_at FROM gmail_mailboxes WHERE alias_key = ?")
          .bind(r.mailbox_key)
          .first<{ expires_at: number }>();
        if (!g) continue;
        out.push({ address: r.display_address, aliasKey: r.mailbox_key, expiresAt: g.expires_at, mode: "gmail" as const });
      } else {
        const m = await c.env.DB.prepare("SELECT expires_at FROM mailboxes WHERE address = ?")
          .bind(r.mailbox_key)
          .first<{ expires_at: number }>();
        if (!m) continue;
        out.push({ address: r.display_address, expiresAt: m.expires_at, mode: "domain" as const });
      }
    }
    return c.json(out);
  });

  app.post("/api/domains", async (c) => {
    const { domain } = await c.req.json();
    const hostname = String(domain || "").toLowerCase().trim();
    if (!hostname.includes(".")) return c.json({ error: "invalid_domain" }, 400);
    const token = crypto.randomUUID().replace(/-/g, "");
    const sid = sessionIdFromRequest(c.req.raw);
    const id = crypto.randomUUID();
    await c.env.DB.prepare(
      `INSERT INTO domains (id, hostname, owner_session_id, verification_token, status, created_at)
       VALUES (?,?,?,?,?,?)
       ON CONFLICT(hostname) DO UPDATE SET
         owner_session_id = excluded.owner_session_id,
         verification_token = excluded.verification_token,
         status = 'pending',
         verified_at = NULL`,
    )
      .bind(id, hostname, sid, token, "pending", Date.now())
      .run();
    return c.json({
      domain: hostname,
      verifyTxt: `tempgmail-verify=${token}`,
      note: "Add this TXT record in Cloudflare DNS, enable Email Routing catch-all for the zone.",
    });
  });

  app.post("/api/domains/:domain/verify", async (c) => {
    const hostname = decodeURIComponent(c.req.param("domain")).toLowerCase();
    const row = await c.env.DB.prepare("SELECT id, verification_token FROM domains WHERE hostname = ?")
      .bind(hostname)
      .first<{ id: string; verification_token: string }>();
    if (!row) return c.json({ error: "not_found" }, 404);
    const expectedTxt = `tempgmail-verify=${row.verification_token}`;
    if (!(await hasTxtRecord(hostname, expectedTxt))) {
      return c.json({ error: "txt_not_found", expectedTxt }, 400);
    }
    await c.env.DB.prepare("UPDATE domains SET status = ?, verified_at = ? WHERE id = ?")
      .bind("verified", Date.now(), row.id)
      .run();
    return c.json({ ok: true, status: "verified", expectedTxt });
  });

  registerAuthRoutes(app);
  registerStripeRoutes(app);
  return app;
}
