CREATE TABLE IF NOT EXISTS mailboxes (
  address TEXT PRIMARY KEY,
  forward_to TEXT,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  session_id TEXT,
  user_id TEXT,
  domain TEXT NOT NULL DEFAULT 'oegmail.store'
);

CREATE TABLE IF NOT EXISTS gmail_mailboxes (
  alias_key TEXT PRIMARY KEY,
  display_address TEXT NOT NULL,
  backing_account TEXT NOT NULL,
  plus_tag TEXT NOT NULL,
  forward_to TEXT,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  session_id TEXT,
  user_id TEXT
);

CREATE TABLE IF NOT EXISTS domains (
  id TEXT PRIMARY KEY,
  hostname TEXT NOT NULL UNIQUE,
  owner_session_id TEXT,
  verification_token TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at INTEGER NOT NULL,
  verified_at INTEGER
);

CREATE TABLE IF NOT EXISTS mailbox_history (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  mailbox_key TEXT NOT NULL,
  display_address TEXT NOT NULL,
  kind TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT,
  created_at INTEGER NOT NULL,
  premium_until INTEGER
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mailboxes_session ON mailboxes(session_id);
CREATE INDEX IF NOT EXISTS idx_gmail_session ON gmail_mailboxes(session_id);
CREATE INDEX IF NOT EXISTS idx_history_session ON mailbox_history(session_id);
CREATE INDEX IF NOT EXISTS idx_mailboxes_user ON mailboxes(user_id);
CREATE INDEX IF NOT EXISTS idx_gmail_user ON gmail_mailboxes(user_id);
CREATE INDEX IF NOT EXISTS idx_mailboxes_user ON mailboxes(user_id);
CREATE INDEX IF NOT EXISTS idx_gmail_user ON gmail_mailboxes(user_id);
