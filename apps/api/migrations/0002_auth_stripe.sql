ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE mailboxes ADD COLUMN user_id TEXT;
ALTER TABLE gmail_mailboxes ADD COLUMN user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_mailboxes_user ON mailboxes(user_id);
CREATE INDEX IF NOT EXISTS idx_gmail_user ON gmail_mailboxes(user_id);
