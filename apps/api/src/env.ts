export interface Env {
  DB: D1Database;
  ATTACHMENTS: R2Bucket;
  MAILBOX: DurableObjectNamespace;
  RATE_LIMIT: KVNamespace;
  TURNSTILE_SITE_KEY: string;
  TURNSTILE_SECRET: string;
  GOOGLE_CLIENT_ID: string;
  GOOGLE_CLIENT_SECRET: string;
  GMAIL_BACKENDS_JSON: string;
  OPERATOR_GMAIL: string;
  DEFAULT_DOMAIN: string;
  BETTER_AUTH_SECRET: string;
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
}
