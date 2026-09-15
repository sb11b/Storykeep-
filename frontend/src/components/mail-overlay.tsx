"use client";

import { useCallback, useEffect, useState } from "react";
import { Inbox, Mail, Pencil, Send, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { sanitizeHtml } from "@/lib/format";
import type { MailMailbox, MailMessage, MailStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const WROTE_MAIL = "storykeep-mail-sent";

function formatWhen(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso || "";
  return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function folderLabel(box: MailMailbox): string {
  const role = (box.role || "").toLowerCase();
  if (role === "inbox") return "Inbox";
  if (role === "sent") return "Sent";
  if (role === "drafts") return "Drafts";
  return box.name;
}

export function MailProposalCard({
  proposal,
  onWrote,
}: {
  proposal: { to: string; subject: string; body: string; status?: string };
  onWrote?: (status: "wrote" | "error") => void;
}) {
  const [busy, setBusy] = useState(false);
  if (proposal.status === "wrote") {
    return <p className="mt-2 text-xs text-muted-foreground">Sent via Fastmail.</p>;
  }
  return (
    <div className="mt-2 rounded-md border bg-background p-2 text-sm">
      <p className="font-medium">{proposal.subject || "(no subject)"}</p>
      <p className="text-xs text-muted-foreground">To {proposal.to}</p>
      <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-xs">{proposal.body}</p>
      <Button
        size="xs"
        className="mt-2"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await api.sendMail({
              to: proposal.to,
              subject: proposal.subject,
              body: proposal.body,
              confirm: true,
            });
            window.dispatchEvent(new Event(WROTE_MAIL));
            onWrote?.("wrote");
            toast.success("Sent.");
          } catch (error) {
            onWrote?.("error");
            toast.error(error instanceof ApiError ? error.message : "Could not send.");
          } finally {
            setBusy(false);
          }
        }}
      >
        Confirm
      </Button>
    </div>
  );
}

export function MailOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [status, setStatus] = useState<MailStatus | null>(null);
  const [mailboxes, setMailboxes] = useState<MailMailbox[]>([]);
  const [role, setRole] = useState("inbox");
  const [mailboxId, setMailboxId] = useState<string | null>(null);
  const [items, setItems] = useState<MailMessage[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState<MailMessage | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingBody, setLoadingBody] = useState(false);
  const [token, setToken] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [compose, setCompose] = useState<{ to: string; subject: string; body: string } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);

  const loadList = useCallback(async (nextRole: string, nextMailboxId: string | null) => {
    setLoading(true);
    try {
      const nextStatus = await api.mailStatus();
      setStatus(nextStatus);
      if (!nextStatus.connected) {
        setItems([]);
        setMailboxes([]);
        setMessage(null);
        return;
      }
      const listed = await api.mailMessages({
        role: nextMailboxId ? undefined : nextRole,
        mailbox_id: nextMailboxId || undefined,
        limit: 50,
      });
      setMailboxes(listed.mailboxes || nextStatus.mailboxes || []);
      setItems(listed.items || []);
      setMessage(null);
      setSelectedId(null);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not load mail.");
      if (error instanceof ApiError && error.status === 401) {
        setStatus((current) =>
          current
            ? { ...current, connected: false }
            : {
                configured: false,
                connected: false,
                owner_only: true,
                is_owner: true,
                demo_locked: false,
                connect_detail: "Connect Fastmail",
              },
        );
      }
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void loadList(role, mailboxId);
  }, [loadList, mailboxId, open, role]);

  useEffect(() => {
    function onSent() {
      if (open) void loadList(role, mailboxId);
    }
    window.addEventListener(WROTE_MAIL, onSent);
    return () => window.removeEventListener(WROTE_MAIL, onSent);
  }, [loadList, mailboxId, open, role]);

  async function openMessage(id: string) {
    setSelectedId(id);
    setLoadingBody(true);
    try {
      const row = await api.mailMessage(id);
      setMessage(row);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not open that message.");
      setMessage(null);
    } finally {
      setLoadingBody(false);
    }
  }

  async function connect() {
    if (token.trim().length < 8) {
      toast.error("Paste a Fastmail API token. It never leaves the server after this request.");
      return;
    }
    setConnecting(true);
    try {
      await api.connectFastmailMail({ token: token.trim() });
      setToken("");
      toast.success("Fastmail mail connected.");
      await loadList("inbox", null);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not connect Fastmail.");
    } finally {
      setConnecting(false);
    }
  }

  async function sendNow() {
    if (!compose) return;
    setSending(true);
    try {
      await api.sendMail({ ...compose, confirm: true });
      toast.success("Sent. Check Sent on Fastmail.");
      setConfirming(false);
      setCompose(null);
      setRole("sent");
      setMailboxId(null);
      window.dispatchEvent(new Event(WROTE_MAIL));
      await loadList("sent", null);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not send.");
    } finally {
      setSending(false);
    }
  }

  if (!open) return null;

  const folders = (mailboxes.length ? mailboxes : status?.mailboxes || []).filter((box) => {
    const roleName = (box.role || "").toLowerCase();
    return roleName === "inbox" || roleName === "sent" || roleName === "drafts" || !box.role;
  });
  const primary = ["inbox", "sent", "drafts"]
    .map((wanted) => folders.find((box) => (box.role || "").toLowerCase() === wanted))
    .filter((box): box is MailMailbox => Boolean(box));
  const extra = folders.filter((box) => !["inbox", "sent", "drafts"].includes((box.role || "").toLowerCase()));
  const shownFolders = [...primary, ...extra].slice(0, 12);

  return (
    <div className="absolute inset-0 z-30 flex min-h-0 flex-col bg-[var(--storykeep-page-bg)]">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2">
        <Mail className="size-4" />
        <h2 className="text-sm font-medium">Mail</h2>
        {status?.fastmail_email ? (
          <span className="text-[11px] text-muted-foreground">{status.fastmail_email}</span>
        ) : null}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {status?.connected ? (
            <Button size="xs" onClick={() => setCompose({ to: "", subject: "", body: "" })}>
              <Pencil className="size-3" />
              Compose
            </Button>
          ) : null}
          <Button size="icon-xs" variant="ghost" onClick={onClose} aria-label="Close mail">
            <X className="size-3.5" />
          </Button>
        </div>
      </div>

      {status == null ? (
        <p className="p-4 text-sm text-muted-foreground">Loading mail…</p>
      ) : status.demo_locked ? (
        <p className="p-4 text-sm text-muted-foreground">Demo accounts cannot use mail.</p>
      ) : !status.is_owner ? (
        <p className="p-4 text-sm text-muted-foreground">Mail is only available on the owner account.</p>
      ) : !status.connected ? (
        <div className="max-w-md space-y-3 p-4">
          <p className="text-sm">Connect Fastmail. StoryKeep reads the Railway token when it is set; otherwise paste an API token. It is stored encrypted and never shown again.</p>
          <div className="space-y-1.5">
            <Label htmlFor="fm-mail-token">Fastmail API token</Label>
            <Input
              id="fm-mail-token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="API token"
            />
          </div>
          <Button size="sm" disabled={connecting} onClick={() => void connect()}>
            Connect Fastmail
          </Button>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[9.5rem_minmax(0,20rem)_minmax(0,1fr)]">
          <nav className="flex shrink-0 gap-1 overflow-auto border-b p-2 md:flex-col md:border-b-0 md:border-r">
            {shownFolders.map((box) => {
              const active = mailboxId ? mailboxId === box.id : (box.role || "inbox") === role;
              return (
                <Button
                  key={box.id}
                  size="xs"
                  variant={active ? "default" : "ghost"}
                  className="justify-start"
                  onClick={() => {
                    setMailboxId(box.role ? null : box.id);
                    setRole(box.role || "inbox");
                  }}
                >
                  {folderLabel(box)}
                  {box.unread ? <span className="ml-auto text-[10px]">{box.unread}</span> : null}
                </Button>
              );
            })}
          </nav>
          <section className="min-h-0 overflow-auto border-b md:border-b-0 md:border-r">
            {loading ? (
              <p className="p-3 text-xs text-muted-foreground">Loading…</p>
            ) : items.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">No messages in this folder.</p>
            ) : (
              <ul>
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={cn(
                        "flex w-full flex-col gap-0.5 border-b px-3 py-2 text-left text-sm hover:bg-muted/50",
                        selectedId === item.id && "bg-muted",
                      )}
                      onClick={() => void openMessage(item.id)}
                    >
                      <span className="flex items-center gap-2">
                        {item.unseen ? <span className="size-1.5 shrink-0 rounded-full bg-primary" /> : <Inbox className="size-3 shrink-0 text-muted-foreground" />}
                        <span className={cn("truncate", item.unseen && "font-medium")}>{item.from || "(no sender)"}</span>
                      </span>
                      <span className="truncate text-xs">{item.subject}</span>
                      <span className="text-[10px] text-muted-foreground">{formatWhen(item.date)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <article className="min-h-0 overflow-auto p-4">
            {loadingBody ? (
              <p className="text-xs text-muted-foreground">Opening…</p>
            ) : message ? (
              <div className="space-y-3">
                <div>
                  <h3 className="font-[family-name:var(--font-serif)] text-lg">{message.subject}</h3>
                  <p className="text-xs text-muted-foreground">From {message.from}</p>
                  {message.to ? <p className="text-xs text-muted-foreground">To {message.to}</p> : null}
                  <p className="text-xs text-muted-foreground">{formatWhen(message.date)}</p>
                </div>
                {message.body_html ? (
                  <div
                    className="prose prose-sm max-w-none text-sm"
                    dangerouslySetInnerHTML={{ __html: sanitizeHtml(message.body_html) }}
                  />
                ) : (
                  <pre className="whitespace-pre-wrap font-sans text-sm">{message.body}</pre>
                )}
                <Button
                  size="xs"
                  variant="outline"
                  onClick={() =>
                    setCompose({
                      to: (message.from.match(/<([^>]+)>/) || [null, message.from])[1] || "",
                      subject: message.subject.startsWith("Re:") ? message.subject : `Re: ${message.subject}`,
                      body: "",
                    })
                  }
                >
                  Reply
                </Button>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Select a message.</p>
            )}
          </article>
        </div>
      )}

      <Dialog open={Boolean(compose) && !confirming} onOpenChange={(next) => !next && setCompose(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Compose</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <div className="space-y-1">
              <Label htmlFor="mail-to">To</Label>
              <Input
                id="mail-to"
                value={compose?.to || ""}
                onChange={(event) => setCompose((current) => (current ? { ...current, to: event.target.value } : current))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="mail-subject">Subject</Label>
              <Input
                id="mail-subject"
                value={compose?.subject || ""}
                onChange={(event) =>
                  setCompose((current) => (current ? { ...current, subject: event.target.value } : current))
                }
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="mail-body">Body</Label>
              <Textarea
                id="mail-body"
                rows={8}
                value={compose?.body || ""}
                onChange={(event) => setCompose((current) => (current ? { ...current, body: event.target.value } : current))}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCompose(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                if (!compose?.to.includes("@") || !compose.body.trim()) {
                  toast.error("To and body are required.");
                  return;
                }
                setConfirming(true);
              }}
            >
              <Send className="size-3" />
              Send
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirming} onOpenChange={(next) => !next && setConfirming(false)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Send this message?</DialogTitle>
          </DialogHeader>
          <div className="space-y-1 text-sm">
            <p>
              <span className="text-muted-foreground">To</span> {compose?.to}
            </p>
            <p>
              <span className="text-muted-foreground">Subject</span> {compose?.subject || "(no subject)"}
            </p>
            <p className="line-clamp-6 whitespace-pre-wrap text-xs">{compose?.body}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(false)}>
              Back
            </Button>
            <Button disabled={sending} onClick={() => void sendNow()}>
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
