import type { Env } from "./env";
import type { InboxMessage } from "@tempgmail/shared";
import { extractPlusTag, fetchGmailMessage, getAccessToken, lookupRefreshToken, maybeForwardGmail } from "./gmail";

const MAX = 100;
const POLL_MS = 15000;

export class MailboxDO implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === "/add" && req.method === "POST") {
      const msg = (await req.json()) as InboxMessage;
      const msgs = ((await this.state.storage.get<InboxMessage[]>("msgs")) ?? []) as InboxMessage[];
      msgs.unshift(msg);
      await this.state.storage.put("msgs", msgs.slice(0, MAX));
      return new Response("ok");
    }
    if (url.pathname === "/list") {
      return Response.json((await this.state.storage.get<InboxMessage[]>("msgs")) ?? []);
    }
    if (url.pathname === "/delete-all" && req.method === "POST") {
      await this.state.storage.deleteAll();
      return new Response("ok");
    }
    if (url.pathname === "/expire" && req.method === "POST") {
      const { at } = (await req.json()) as { at: number };
      await this.state.storage.setAlarm(at);
      return new Response("ok");
    }
    if (url.pathname === "/poll-start" && req.method === "POST") {
      const body = (await req.json()) as { account: string; tag: string; aliasKey: string; expiresAt: number };
      await this.state.storage.put("active", true);
      await this.state.storage.put("account", body.account);
      await this.state.storage.put("tag", body.tag);
      await this.state.storage.put("aliasKey", body.aliasKey);
      await this.state.storage.put("expiresAt", body.expiresAt);
      await this.state.storage.setAlarm(Date.now() + POLL_MS);
      return new Response("ok");
    }
    if (url.pathname === "/mark-read" && req.method === "POST") {
      const { id } = (await req.json()) as { id: string };
      const msgs = ((await this.state.storage.get<InboxMessage[]>("msgs")) ?? []) as InboxMessage[];
      const next = msgs.map((m) => (m.id === id ? { ...m, read: true } : m));
      await this.state.storage.put("msgs", next);
      return new Response("ok");
    }
    return new Response("not found", { status: 404 });
  }

  async alarm() {
    const active = await this.state.storage.get<boolean>("active");
    const expiresAt = await this.state.storage.get<number>("expiresAt");
    if (expiresAt && expiresAt <= Date.now()) {
      await this.state.storage.deleteAll();
      return;
    }
    if (active) {
      await this.pollGmail();
      await this.state.storage.setAlarm(Date.now() + POLL_MS);
      return;
    }
    await this.state.storage.deleteAll();
  }

  private async pollGmail() {
    const account = await this.state.storage.get<string>("account");
    const tag = await this.state.storage.get<string>("tag");
    const aliasKey = await this.state.storage.get<string>("aliasKey");
    if (!account || !tag || !aliasKey) return;
    const refresh = await lookupRefreshToken(this.env, account);
    if (!refresh) return;
    const token = await getAccessToken(this.env, refresh);
    const local = account.split("@")[0];
    const q = encodeURIComponent(`to:(${local}+${tag}@gmail.com) newer_than:1d`);
    const list = (await fetch(`https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${q}`, {
      headers: { authorization: `Bearer ${token}` },
    }).then((r) => r.json())) as { messages?: { id: string }[] };
    for (const m of list.messages ?? []) {
      const msg = await fetchGmailMessage(this.env, token, m.id, aliasKey);
      if (!msg) continue;
      if (extractPlusTag(msg.to) !== tag.toLowerCase()) continue;
      const msgs = ((await this.state.storage.get<InboxMessage[]>("msgs")) ?? []) as InboxMessage[];
      if (msgs.find((x) => x.id === msg.id)) continue;
      msgs.unshift(msg);
      await this.state.storage.put("msgs", msgs.slice(0, MAX));
      await maybeForwardGmail(this.env, token, aliasKey, msg);
    }
  }
}
