import QRCode from "qrcode";
import { useEffect, useState } from "react";
import type { MailboxResp } from "../lib/api";
import { api } from "../lib/api";

type Props = {
  mailbox: MailboxResp;
  mailboxKey: string;
  onDeleted: () => void;
  premium?: boolean;
};

export function Toolbar({ mailbox, mailboxKey, onDeleted, premium = false }: Props) {
  const [qr, setQr] = useState("");
  const [showQr, setShowQr] = useState(false);
  const [fwd, setFwd] = useState("");
  const base = mailbox.mode === "gmail" ? "/api/gmail-mailbox" : "/api/mailbox";

  useEffect(() => {
    QRCode.toDataURL(mailbox.address, { width: 120, margin: 1 }).then(setQr);
  }, [mailbox.address]);

  const del = async () => {
    await api(`${base}/${encodeURIComponent(mailboxKey)}`, { method: "DELETE" });
    onDeleted();
  };

  const saveFwd = async () => {
    if (!premium) return;
    await api(`${base}/${encodeURIComponent(mailboxKey)}/forward`, {
      method: "POST",
      body: JSON.stringify({ forwardTo: fwd || null }),
    });
  };

  return (
    <div className="toolbar">
      <button type="button" className="tool-btn" onClick={del}><span>Delete</span></button>
      <button type="button" className="tool-btn" onClick={() => setShowQr((v) => !v)}><span>QR Code</span></button>
      {premium ? (
        <label className="fwd tool-wide">
          <span>Email Forward</span>
          <input value={fwd} onChange={(e) => setFwd(e.target.value)} placeholder="you@example.com" />
          <button type="button" onClick={saveFwd}>Save</button>
        </label>
      ) : (
        <span className="fwd muted tool-wide">Email Forward <b>NEW</b></span>
      )}
      {showQr && qr && (
        <div className="qr-popover">
          <img src={qr} alt="QR code for mailbox address" className="qr" />
        </div>
      )}
    </div>
  );
}
