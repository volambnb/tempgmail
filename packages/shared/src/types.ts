export type MailboxMode = "domain" | "gmail";
export interface AttachmentMeta { id: string; key: string; name: string; type: string }
export interface InboxMessage {
  id: string; from: string; to?: string; subject: string; text: string; html: string;
  attachments: AttachmentMeta[]; receivedAt: number; read: boolean;
}
export interface MailboxResponse {
  mode: MailboxMode; address: string; mailboxKey: string; expiresAt: number;
}
export interface HistoryItem {
  mode: MailboxMode; address: string; mailboxKey: string; createdAt: number; expiresAt: number;
}
