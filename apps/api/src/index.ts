import { cleanupExpired } from "./cleanup";
import type { Env } from "./env";
import { MailboxDO } from "./mailbox-do";
import { createApp } from "./routes";

export { MailboxDO };

export default {
  fetch: createApp().fetch,
  scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(cleanupExpired(env).then((res) => res.text()).then(console.log));
  },
};
