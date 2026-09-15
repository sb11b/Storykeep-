"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";
import {
  addDays,
  formatEventWhen,
  fromLocalInput,
  localInputValue,
  monthGridRange,
  sameDay,
  startOfMonth,
  toRfc3339,
  weekRange,
} from "@/lib/calendar-range";
import type { CalendarEvent, CalendarStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const WROTE_EVENT = "storykeep-calendar-wrote";

function tzName() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

function emptyDraft(start: Date) {
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  return { id: null as string | null, title: "", start: localInputValue(start.toISOString()), end: localInputValue(end.toISOString()) };
}

export function CalendarOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [view, setView] = useState<"week" | "month">("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const [status, setStatus] = useState<CalendarStatus | null>(null);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [editor, setEditor] = useState<ReturnType<typeof emptyDraft> | null>(null);
  const [saving, setSaving] = useState(false);
  const [fmEmail, setFmEmail] = useState("");
  const [fmToken, setFmToken] = useState("");
  const [fmCalendarUrl, setFmCalendarUrl] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [emptyCalendars, setEmptyCalendars] = useState(false);

  const range = useMemo(() => (view === "week" ? weekRange(anchor) : monthGridRange(anchor)), [anchor, view]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const nextStatus = await api.calendarStatus();
      setStatus(nextStatus);
      if (!nextStatus.connected) {
        setEvents([]);
        return;
      }
      const payload = await api.calendarEvents({
        view,
        time_min: toRfc3339(range.start),
        time_max: toRfc3339(range.end),
        tz: tzName(),
      });
      setEvents(payload.items || []);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not load the calendar.");
      setStatus((current) =>
        current || {
          configured: true,
          connected: false,
          provider: null,
          fastmail_configured: true,
          fastmail_email: null,
          demo_locked: false,
        },
      );
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [range.end, range.start, view]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [load, open]);

  useEffect(() => {
    function onWrote() {
      if (open) void load();
    }
    window.addEventListener(WROTE_EVENT, onWrote);
    return () => window.removeEventListener(WROTE_EVENT, onWrote);
  }, [load, open]);

  async function connectFastmail(retry = false) {
    if (!fmEmail.trim() || fmToken.trim().length < 8) {
      toast.error("Use your Fastmail email and an app password or API token.");
      return;
    }
    setConnecting(true);
    if (!retry) setEmptyCalendars(false);
    try {
      const calendarUrl = fmCalendarUrl.trim();
      await api.connectFastmailCalendar({
        email: fmEmail.trim(),
        token: fmToken,
        ...(calendarUrl ? { calendar_url: calendarUrl } : {}),
      });
      setFmToken("");
      setEmptyCalendars(false);
      toast.success("Fastmail Calendar connected.");
      await load();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Could not connect Fastmail.";
      if (message.includes("No calendars")) {
        setEmptyCalendars(true);
        toast.error("No calendars — create one on Fastmail.com");
      } else {
        toast.error(message);
      }
    } finally {
      setConnecting(false);
    }
  }

  async function saveEditor() {
    if (!editor?.title.trim()) {
      toast.error("Add a title.");
      return;
    }
    setSaving(true);
    try {
      const body = { title: editor.title.trim(), start: fromLocalInput(editor.start), end: fromLocalInput(editor.end) };
      if (editor.id) await api.patchCalendarEvent(editor.id, body, tzName());
      else await api.createCalendarEvent(body, tzName());
      setEditor(null);
      await load();
      toast.success(editor.id ? "Event updated." : "Event added.");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not save that event.");
    } finally {
      setSaving(false);
    }
  }

  async function removeEditor() {
    if (!editor?.id) return;
    setSaving(true);
    try {
      await api.deleteCalendarEvent(editor.id);
      setEditor(null);
      await load();
      toast.success("Event deleted.");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not delete that event.");
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;

  const days = view === "week" ? Array.from({ length: 7 }, (_, i) => addDays(range.start, i)) : Array.from({ length: 42 }, (_, i) => addDays(range.start, i));
  const label =
    view === "week"
      ? `${range.start.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${addDays(range.end, -1).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`
      : startOfMonth(anchor).toLocaleDateString(undefined, { month: "long", year: "numeric" });

  return (
    <div className="absolute inset-0 z-30 flex min-h-0 flex-col bg-[var(--storykeep-page-bg)]">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2">
        <CalendarDays className="size-4" />
        <h2 className="text-sm font-medium">Calendar</h2>
        <div className="flex items-center gap-1">
          <Button size="icon-xs" variant="outline" onClick={() => setAnchor((current) => addDays(current, view === "week" ? -7 : -28))} aria-label="Previous">
            <ChevronLeft className="size-3.5" />
          </Button>
          <Button size="xs" variant="outline" onClick={() => setAnchor(new Date())}>
            Today
          </Button>
          <Button size="icon-xs" variant="outline" onClick={() => setAnchor((current) => addDays(current, view === "week" ? 7 : 28))} aria-label="Next">
            <ChevronRight className="size-3.5" />
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">{label}</p>
        <div className="flex rounded-md border">
          <Button size="xs" variant={view === "week" ? "default" : "ghost"} className="rounded-r-none" onClick={() => setView("week")}>
            Week
          </Button>
          <Button size="xs" variant={view === "month" ? "default" : "ghost"} className="rounded-l-none" onClick={() => setView("month")}>
            Month
          </Button>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {status?.connected ? (
            <>
              <span className="text-[11px] text-muted-foreground">
                {status.fastmail_email || status.calendar_name || "Fastmail Calendar"}
              </span>
              <Button size="xs" variant="outline" onClick={() => setEditor(emptyDraft(new Date()))}>
                New event
              </Button>
              <Button
                size="xs"
                variant="ghost"
                onClick={async () => {
                  try {
                    await api.disconnectCalendar();
                    toast.success("Calendar disconnected.");
                    await load();
                  } catch (error) {
                    toast.error(error instanceof ApiError ? error.message : "Could not disconnect.");
                  }
                }}
              >
                Disconnect
              </Button>
            </>
          ) : null}
          <Button size="icon-xs" variant="ghost" onClick={onClose} aria-label="Close calendar">
            <X className="size-3.5" />
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {status === null ? (
          <p className="text-sm text-muted-foreground">Loading calendar…</p>
        ) : status.demo_locked ? (
          <p className="text-sm text-muted-foreground">Demo accounts cannot connect Fastmail Calendar.</p>
        ) : !status?.connected ? (
          <div className="flex max-w-md flex-col gap-3">
            <p className="text-sm">
              Connect Fastmail Calendar to see this week. Use an app password or API token from Fastmail Settings — never your account password. Mail stays off until a later phase.
            </p>
            <div className="flex flex-col gap-2">
              <Label htmlFor="fm-email">Fastmail email</Label>
              <Input
                id="fm-email"
                type="email"
                autoComplete="username"
                value={fmEmail}
                onChange={(event) => setFmEmail(event.target.value)}
              />
              <Label htmlFor="fm-token">App password or API token</Label>
              <Input
                id="fm-token"
                type="password"
                autoComplete="off"
                value={fmToken}
                onChange={(event) => setFmToken(event.target.value)}
              />
              <Label htmlFor="fm-cal-url">Calendar URL (optional)</Label>
              <Input
                id="fm-cal-url"
                type="url"
                autoComplete="off"
                placeholder="https://caldav.fastmail.com/dav/calendars/user/you@fastmail.com/…"
                value={fmCalendarUrl}
                onChange={(event) => setFmCalendarUrl(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Leave blank to discover calendars. Or paste the CalDAV URL from Fastmail Settings → Calendars.
              </p>
              <Button disabled={connecting} onClick={() => void connectFastmail(false)}>
                Connect Fastmail
              </Button>
              {emptyCalendars ? (
                <div className="flex flex-col gap-2 rounded-md border p-2">
                  <p className="text-sm">No calendars — create one on Fastmail.com</p>
                  <Button variant="outline" disabled={connecting} onClick={() => void connectFastmail(true)}>
                    Retry
                  </Button>
                </div>
              ) : null}
            </div>
          </div>
        ) : loading ? (
          <p className="text-sm text-muted-foreground">Loading events…</p>
        ) : (
          <div className={cn("grid gap-px rounded-md border bg-border", view === "week" ? "grid-cols-7" : "grid-cols-7")}>
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((name) => (
              <div key={name} className="bg-muted/40 px-2 py-1 text-[11px] font-medium text-muted-foreground">
                {name}
              </div>
            ))}
            {days.map((day) => {
              const dayEvents = events.filter((item) => {
                const start = new Date(item.start);
                return !Number.isNaN(start.getTime()) && sameDay(start, day);
              });
              const inMonth = day.getMonth() === anchor.getMonth();
              return (
                <button
                  key={day.toISOString()}
                  type="button"
                  className={cn(
                    "min-h-24 bg-background p-1 text-left align-top",
                    view === "month" && !inMonth && "bg-muted/20 text-muted-foreground",
                    sameDay(day, new Date()) && "ring-1 ring-inset ring-primary/40",
                  )}
                  onClick={() => {
                    const start = new Date(day);
                    start.setHours(9, 0, 0, 0);
                    setEditor(emptyDraft(start));
                  }}
                >
                  <span className="text-[11px] font-medium">{day.getDate()}</span>
                  <ul className="mt-1 space-y-0.5">
                    {dayEvents.map((item) => (
                      <li key={item.id}>
                        <span
                          className="block truncate rounded bg-primary/10 px-1 text-[11px] text-foreground"
                          onClick={(event) => {
                            event.stopPropagation();
                            setEditor({
                              id: item.id,
                              title: item.title,
                              start: localInputValue(item.start),
                              end: localInputValue(item.end),
                            });
                          }}
                        >
                          {item.title}
                        </span>
                      </li>
                    ))}
                  </ul>
                </button>
              );
            })}
          </div>
        )}
      </div>
      <Dialog open={Boolean(editor)} onOpenChange={(next) => !next && setEditor(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editor?.id ? "Edit event" : "New event"}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="cal-title">Title</Label>
            <Input id="cal-title" value={editor?.title || ""} onChange={(event) => setEditor((current) => current && { ...current, title: event.target.value })} />
            <Label htmlFor="cal-start">Start</Label>
            <Input id="cal-start" type="datetime-local" value={editor?.start || ""} onChange={(event) => setEditor((current) => current && { ...current, start: event.target.value })} />
            <Label htmlFor="cal-end">End</Label>
            <Input id="cal-end" type="datetime-local" value={editor?.end || ""} onChange={(event) => setEditor((current) => current && { ...current, end: event.target.value })} />
          </div>
          <DialogFooter className="gap-2">
            {editor?.id ? (
              <Button variant="destructive" disabled={saving} onClick={() => void removeEditor()}>
                Delete
              </Button>
            ) : null}
            <Button variant="outline" onClick={() => setEditor(null)}>
              Cancel
            </Button>
            <Button disabled={saving} onClick={() => void saveEditor()}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function CalendarProposalCard({
  proposal,
  onWrote,
}: {
  proposal: { title: string; start: string; end: string; status?: string };
  onWrote?: (status: "wrote" | "error") => void;
}) {
  const [busy, setBusy] = useState(false);
  if (proposal.status === "wrote") {
    return <p className="mt-2 text-xs text-muted-foreground">Added to your calendar.</p>;
  }
  return (
    <div className="mt-2 rounded-md border bg-background p-2 text-sm">
      <p className="font-medium">{proposal.title}</p>
      <p className="text-xs text-muted-foreground">
        {formatEventWhen(proposal.start)} – {formatEventWhen(proposal.end)}
      </p>
      <Button
        size="xs"
        className="mt-2"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await api.createCalendarEvent({ title: proposal.title, start: proposal.start, end: proposal.end }, tzName());
            window.dispatchEvent(new Event(WROTE_EVENT));
            onWrote?.("wrote");
            toast.success("Event added to your calendar.");
          } catch (error) {
            onWrote?.("error");
            toast.error(error instanceof ApiError ? error.message : "Could not add that event.");
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
