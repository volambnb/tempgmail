import type { Env } from "./env";

const RETENTION_MS = 24 * 60 * 60 * 1000;
const BATCH = 100;

type ExpiredDomainMailbox = {
  address: string;
};

type ExpiredGmailMailbox = {
  alias_key: string;
  display_address: string;
};

async function deleteR2Prefix(env: Env, prefix: string): Promise<number> {
  let cursor: string | undefined;
  let deleted = 0;
  do {
    const listed = await env.ATTACHMENTS.list({ prefix, cursor, limit: 100 });
    await Promise.all(listed.objects.map((obj) => env.ATTACHMENTS.delete(obj.key)));
    deleted += listed.objects.length;
    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);
  return deleted;
}

async function clearMailboxDO(env: Env, key: string): Promise<void> {
  const stub = env.MAILBOX.get(env.MAILBOX.idFromName(key.toLowerCase()));
  await stub.fetch("https://do/delete-all", { method: "POST" });
}

export async function cleanupExpired(env: Env, now = Date.now()): Promise<Response> {
  const cutoff = now - RETENTION_MS;
  const domainRows = await env.DB.prepare(
    "SELECT address FROM mailboxes WHERE expires_at < ? ORDER BY expires_at ASC LIMIT ?",
  )
    .bind(cutoff, BATCH)
    .all<ExpiredDomainMailbox>();
  const gmailRows = await env.DB.prepare(
    "SELECT alias_key, display_address FROM gmail_mailboxes WHERE expires_at < ? ORDER BY expires_at ASC LIMIT ?",
  )
    .bind(cutoff, BATCH)
    .all<ExpiredGmailMailbox>();

  let r2Deleted = 0;
  for (const row of domainRows.results ?? []) {
    await clearMailboxDO(env, row.address);
    r2Deleted += await deleteR2Prefix(env, `att/${row.address.toLowerCase()}/`);
    await env.DB.prepare("DELETE FROM mailboxes WHERE address = ?").bind(row.address.toLowerCase()).run();
  }

  for (const row of gmailRows.results ?? []) {
    await clearMailboxDO(env, row.alias_key);
    r2Deleted += await deleteR2Prefix(env, `att/${row.alias_key}/`);
    r2Deleted += await deleteR2Prefix(env, `att/${row.display_address.toLowerCase()}/`);
    await env.DB.prepare("DELETE FROM gmail_mailboxes WHERE alias_key = ?").bind(row.alias_key).run();
  }

  const history = await env.DB.prepare("DELETE FROM mailbox_history WHERE created_at < ?")
    .bind(cutoff)
    .run();
  const sessions = await env.DB.prepare("DELETE FROM sessions WHERE expires_at < ?")
    .bind(now)
    .run();

  return Response.json({
    ok: true,
    cutoff,
    mailboxesDeleted: domainRows.results?.length ?? 0,
    gmailDeleted: gmailRows.results?.length ?? 0,
    r2Deleted,
    historyDeleted: history.meta.changes ?? 0,
    sessionsDeleted: sessions.meta.changes ?? 0,
  });
}
