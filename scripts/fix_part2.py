from pathlib import Path
ROOT=Path(r'D:\codex\tempgmail')
(ROOT/'apps/api/src/routes.ts').write_text(r'''import { Hono } from "hono";
import type { Env } from "./env";
import { allowRate, randomLocal, sessionIdFromRequest, verifyTurnstile } from "./security";
import { dotify, pickBackingGmail } from "./gmail";

const DEFAULT_DOMAIN = "oegmail.store";
const TTL_MS = 3600_000;

export function createApp() {
  const app = new Hono<{ Bindings: Env }>();

  async function guard(c: any) {
    const body = await c.req.json().catch(() => ({}));
    const ip = c.req.header("CF-Connecting-IP") ?? "0.0.0.0";
    const token = body.turnstileToken as string | undefined;
    if (c.env.TURNSTILE_SECRET && !(await verifyTurnstile(token, ip, c.env))) {
      return { ok: false as const, res: c.json({ error: "captcha" }, 403) };
    }
    if (!(await allowRate(c.env, ip))) {
      return { ok: false as const, res: c.json({ error: "rate" }, 429) };
    }
    return { ok: true as const, body, ip };
  }

  function mailboxStub(env: Env, key: string) {
    return env.MAILBOX.get(env.MAILBOX.idFromName(key.toLowerCase()));
  }

  app.post("/api/mailbox", async (c) => {
    const g = await guard(c);
    if (!g.ok) return g.res;
    const domain = c.env.DEFAULT_DOMAIN || DEFAULT_DOMAIN;
    const address = `${randomLocal()}@${domain}`.toLowerCase();
    const expiresAt = Date.now() + TTL_MS;
    const sid = sessionIdFromRequest(c.req.raw);
    await c.env.DB.prepare(
      "INSERT INTO mailboxes (address, domain, session_id, expires_at, created_at) VALUES (?,?,?,?,?)",
    )
      .bind(address, domain, sid, expiresAt, Date.now())
      .run();
    const stub = mailboxStub(c.env, address);
    await stub.fetch("https://do/expire", { method: "POST", body: JSON.stringify({ at: expiresAt }) });
    return c.json({ address, expiresAt, mode: "domain" });
  });

  app.post("/api/gmail-mailbox", async (c) => {
    const g = await guard(c);
    if (!g.ok) return g.res;
    let account;
    try {
      account = pickBackingGmail(c.env);
    } catch {
      return c.json({ error: "no_gmail_backend" }, 503);
    }
    const tag = crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    const display = `${dotify(account.local)}+${tag}@gmail.com`;
    const aliasKey = `${account.email}#${tag}`;
    const expiresAt = Date.now() + TTL_MS;
    const sid = sessionIdFromRequest(c.req.raw);
    await c.env.DB.prepare(
      "INSERT INTO gmail_mailboxes (alias_key, display_address, backing_account, plus_tag, session_id, expires_at, created_at) VALUES (?,?,?,?,?,?,?)",
    )
      .bind(aliasKey, display, account.email, tag, sid, expiresAt, Date.now())
      .run();
    const stub = mailboxStub(c.env, aliasKey);
    await stub.fetch("https://do/expire", { method: "POST", body: JSON.stringify({ at: expiresAt }) });
    await stub.fetch("https://do/poll-start", {
      method: "POST",
      body: JSON.stringify({ account: account.email, tag, aliasKey }),
    });
    return c.json({ address: display, aliasKey, expiresAt, mode: "gmail" });
  });

  app.get("/api/mailbox/:key/messages", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    const stub = mailboxStub(c.env, key);
    return stub.fetch("https://do/list");
  });

  app.get("/api/gmail-mailbox/:key/messages", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    const stub = mailboxStub(c.env, key);
    return stub.fetch("https://do/list");
  });

  app.post("/api/mailbox/:key/read", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    const { id } = await c.req.json();
    const stub = mailboxStub(c.env, key);
    await stub.fetch("https://do/mark-read", { method: "POST", body: JSON.stringify({ id }) });
    return c.json({ ok: true });
  });

  app.post("/api/gmail-mailbox/:key/read", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    const { id } = await c.req.json();
    const stub = mailboxStub(c.env, key);
    await stub.fetch("https://do/mark-read", { method: "POST", body: JSON.stringify({ id }) });
    return c.json({ ok: true });
  });

  app.delete("/api/mailbox/:key", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    const stub = mailboxStub(c.env, key);
    await stub.fetch("https://do/delete-all", { method: "POST" });
    await c.env.DB.prepare("DELETE FROM mailboxes WHERE address = ?").bind(key.toLowerCase()).run();
    return c.json({ ok: true });
  });

  app.delete("/api/gmail-mailbox/:key", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    const stub = mailboxStub(c.env, key);
    await stub.fetch("https://do/delete-all", { method: "POST" });
    await c.env.DB.prepare("DELETE FROM gmail_mailboxes WHERE alias_key = ?").bind(key).run();
    return c.json({ ok: true });
  });

  app.get("/api/history", async (c) => {
    const sid = sessionIdFromRequest(c.req.raw);
    const domainRows = await c.env.DB.prepare(
      "SELECT address, expires_at, created_at FROM mailboxes WHERE session_id = ? ORDER BY created_at DESC LIMIT 20",
    )
      .bind(sid)
      .all();
    const gmailRows = await c.env.DB.prepare(
      "SELECT display_address as address, alias_key, expires_at, created_at FROM gmail_mailboxes WHERE session_id = ? ORDER BY created_at DESC LIMIT 20",
    )
      .bind(sid)
      .all();
    return c.json({ domain: domainRows.results ?? [], gmail: gmailRows.results ?? [] });
  });

  app.post("/api/mailbox/:key/forward", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    const { forwardTo } = await c.req.json();
    const fwd = forwardTo ? String(forwardTo).trim() : null;
    await c.env.DB.prepare("UPDATE mailboxes SET forward_to = ? WHERE address = ?")
      .bind(fwd, key.toLowerCase())
      .run();
    return c.json({ ok: true, forwardTo: fwd });
  });

  app.post("/api/gmail-mailbox/:key/forward", async (c) => {
    const key = decodeURIComponent(c.req.param("key"));
    const { forwardTo } = await c.req.json();
    const fwd = forwardTo ? String(forwardTo).trim() : null;
    await c.env.DB.prepare("UPDATE gmail_mailboxes SET forward_to = ? WHERE alias_key = ?")
      .bind(fwd, key)
      .run();
    return c.json({ ok: true, forwardTo: fwd });
  });

  app.post("/api/domains", async (c) => {
    const g = await guard(c);
    if (!g.ok) return g.res;
    const { domain } = g.body as { domain?: string };
    if (!domain) return c.json({ error: "domain_required" }, 400);
    const token = crypto.randomUUID().replace(/-/g, "").slice(0, 16);
    const sid = sessionIdFromRequest(c.req.raw);
    await c.env.DB.prepare(
      "INSERT INTO domains (domain, owner_session_id, verify_token, verified, created_at) VALUES (?,?,?,?,?)",
    )
      .bind(domain.toLowerCase(), sid, token, 0, Date.now())
      .run();
    return c.json({
      domain: domain.toLowerCase(),
      verifyTxt: `tempgmail-verify=${token}`,
      note: "Add domain to Cloudflare zone and Email Routing catch-all to receive mail.",
    });
  });

  app.post("/api/domains/:domain/verify", async (c) => {
    const domain = c.req.param("domain").toLowerCase();
    const row = await c.env.DB.prepare("SELECT verify_token FROM domains WHERE domain = ?")
      .bind(domain)
      .first<{ verify_token: string }>();
    if (!row) return c.json({ error: "not_found" }, 404);
    await c.env.DB.prepare("UPDATE domains SET verified = 1 WHERE domain = ?").bind(domain).run();
    return c.json({ ok: true, domain, verified: true, expectedTxt: `tempgmail-verify=${row.verify_token}` });
  });

  app.get("/api/attachments/*", async (c) => {
    const key = c.req.path.replace("/api/attachments/", "");
    const obj = await c.env.ATTACHMENTS.get(key);
    if (!obj) return c.notFound();
    return new Response(obj.body, {
      headers: { "content-type": obj.httpMetadata?.contentType ?? "application/octet-stream" },
    });
  });

  app.get("/api/health", (c) => c.json({ ok: true }));

  return app;
}
''', encoding='utf-8')
print('routes ok')
