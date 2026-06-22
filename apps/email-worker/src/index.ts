import PostalMime from "postal-mime";

export interface Env {
  DB: D1Database;
  ATTACHMENTS: R2Bucket;
  MAILBOX: DurableObjectNamespace;
}

export default {
  async email(message: ForwardableEmailMessage, env: Env, ctx: ExecutionContext) {
    const to = message.to.toLowerCase();
    const row = await env.DB.prepare(
      "SELECT forward_to, expires_at FROM mailboxes WHERE address = ?",
    )
      .bind(to)
      .first<{ forward_to: string | null; expires_at: number }>();
    if (!row || row.expires_at < Date.now()) {
      message.setReject("550 5.1.1 Mailbox unavailable");
      return;
    }
    const raw = await new Response(message.raw).arrayBuffer();
    const email = await new PostalMime().parse(raw);
    const attachments: { id: string; key: string; name: string; type: string }[] = [];
    for (const att of email.attachments ?? []) {
      const id = crypto.randomUUID();
      const key = `att/${to}/${id}`;
      await env.ATTACHMENTS.put(key, att.content, {
        httpMetadata: { contentType: att.mimeType },
      });
      attachments.push({ id, key, name: att.filename ?? "file", type: att.mimeType ?? "application/octet-stream" });
    }
    const msg = {
      id: crypto.randomUUID(),
      from: email.from?.address ?? "",
      subject: email.subject ?? "(no subject)",
      text: email.text ?? "",
      html: email.html ?? "",
      attachments,
      receivedAt: Date.now(),
      read: false,
    };
    const stub = env.MAILBOX.get(env.MAILBOX.idFromName(to));
    ctx.waitUntil(stub.fetch("https://do/add", { method: "POST", body: JSON.stringify(msg) }));
    if (row.forward_to) await message.forward(row.forward_to);
  },
};
