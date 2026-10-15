// Semantic telemetry only: no keystroke contents or continuous cursor coordinates.
export type Region = "question" | "answers" | "submit" | "chat" | "chat_input" | "suggestions" | "reference" | "agent_A" | "agent_B" | "other";
export type EventData = {
  region?: Region; duration_ms?: number; visible_ms?: number; focused_ms?: number;
  active_ms?: number; pointer_ms?: number; unobserved_ms?: number; pointer_type?: string; request_id?: string;
  item_id?: string; agent?: "default" | "A" | "B"; position?: number; text?: string;
  url?: string; choice_id?: string; trigger?: "manual" | "followup_chip" | "auto_question";
  visible?: boolean; viewport_width?: number; viewport_height?: number;
};
type Event = {
  event_id: string; event_type: string; conversation_id: string; question_id: string;
  page_id: string; sequence: number; occurred_at: string; elapsed_ms: number; data: EventData;
};
export type ResearchContext = { userId: string; conversationId: string; questionId: string };

class EventQueue {
  private events: Event[] = [];
  private sending = false;
  private key: string;
  private recoveredKeys: string[] = [];
  constructor(userId: string) {
    const prefix = `mep.research.v1.${userId}`;
    // Each tab writes its own queue. Recovery may resend another tab's events,
    // which the server deduplicates; concurrent tabs cannot overwrite new events.
    this.key = `${prefix}.${crypto.randomUUID()}`;
    try {
      for (let index = 0; index < localStorage.length; index++) {
        const key = localStorage.key(index)!;
        if (key !== prefix && !key.startsWith(`${prefix}.`)) continue;
        const events = JSON.parse(localStorage.getItem(key) || "[]");
        if (Array.isArray(events)) { this.events.push(...events); this.recoveredKeys.push(key); }
      }
      this.events = [...new Map(this.events.map(event => [event.event_id, event])).values()];
    } catch { /* storage disabled */ }
  }
  private persist() {
    try {
      if (this.events.length) localStorage.setItem(this.key, JSON.stringify(this.events));
      else localStorage.removeItem(this.key);
    } catch { /* in-memory delivery remains available */ }
  }
  add(event: Event) {
    this.events.push(event);
    // Sequence gaps make overflow detectable in the research export.
    if (this.events.length > 2000) this.events.splice(0, this.events.length - 2000);
    this.persist();
  }
  async flush() {
    if (this.sending || !this.events.length) return;
    this.sending = true;
    try {
      while (this.events.length) {
        const batch: Event[] = [];
        for (const event of this.events.slice(0, 50)) {
          if (batch.length && new Blob([JSON.stringify({ events: [...batch, event] })]).size > 48000) break;
          batch.push(event);
        }
        const response = await fetch("/api/research/events", {
          method: "POST", credentials: "include", keepalive: true,
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ events: batch }),
        });
        if (!response.ok) break; // Preserve the same IDs for a later retry, including expired sessions.
        const ids = new Set(batch.map(event => event.event_id));
        this.events = this.events.filter(event => !ids.has(event.event_id));
        for (const key of this.recoveredKeys) {
          try {
            const remaining = (JSON.parse(localStorage.getItem(key) || "[]") as Event[]).filter(event => !ids.has(event.event_id));
            if (remaining.length) localStorage.setItem(key, JSON.stringify(remaining));
            else localStorage.removeItem(key);
          } catch { /* recovery is best effort */ }
        }
        this.persist();
      }
    } catch { /* offline: retry on next interval or next study page */ }
    finally { this.sending = false; }
  }
}

const queues = new Map<string, EventQueue>();
function queueFor(userId: string) {
  if (!queues.has(userId)) queues.set(userId, new EventQueue(userId));
  return queues.get(userId)!;
}

export function regionFor(target: EventTarget | null): Region {
  return (target instanceof Element ? target.closest<HTMLElement>("[data-research-region]")?.dataset.researchRegion as Region : undefined) || "other";
}

export class QuestionResearch {
  readonly pageId = crypto.randomUUID();
  private sequence = 0;
  private origin = performance.now();
  private queue: EventQueue;
  constructor(readonly context: ResearchContext) { this.queue = queueFor(context.userId); }
  emit = (event_type: string, data: EventData = {}) => {
    this.queue.add({ event_id: crypto.randomUUID(), event_type, conversation_id: this.context.conversationId,
      question_id: this.context.questionId, page_id: this.pageId, sequence: this.sequence++,
      occurred_at: new Date().toISOString(), elapsed_ms: performance.now() - this.origin, data });
  };
  flush = () => this.queue.flush();
  submissionContext = () => ({ telemetry_page_id: this.pageId, telemetry_elapsed_ms: performance.now() - this.origin });
  start(root: HTMLElement) {
    const seen = new Set<string>();
    const observed = new WeakSet<Element>();
    let lastTick = performance.now();
    let lastActivity = lastTick;
    let pointerRegion: Region = "other";
    let pointerPresent = false;
    let focused = document.hasFocus();
    let visible = document.visibilityState !== "hidden";
    const tick = () => {
      const now = performance.now();
      // A suspended browser timer is unobserved time, not continuous engagement.
      const duration = Math.min(15000, Math.max(0, now - lastTick));
      const active = visible && focused ? Math.max(0, Math.min(now, lastActivity + 60000) - lastTick) : 0;
      if (duration > 0) this.emit("activity_interval", {
        region: pointerRegion, duration_ms: duration, visible_ms: visible ? duration : 0,
        focused_ms: visible && focused ? duration : 0, active_ms: Math.min(duration, active),
        pointer_ms: visible && focused && pointerPresent ? duration : 0,
        unobserved_ms: Math.max(0, now - lastTick - duration),
      });
      lastTick = now;
    };
    const activity = () => { lastActivity = performance.now(); };
    const move = (event: PointerEvent) => {
      const next = regionFor(event.target);
      if (next !== pointerRegion || !pointerPresent) tick();
      pointerRegion = next;
      pointerPresent = event.pointerType !== "touch";
      activity();
    };
    const leave = () => { tick(); pointerPresent = false; pointerRegion = "other"; };
    const click = (event: MouseEvent) => {
      activity();
      this.emit("region_click", { region: regionFor(event.target) });
      const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[data-research-kind="reference_displayed"]') : null;
      if (anchor && (!anchor.dataset.researchQuestion || anchor.dataset.researchQuestion === this.context.questionId)) {
        this.emit("reference_clicked", { item_id: anchor.dataset.researchItem,
          request_id: anchor.dataset.researchRequest, url: anchor.href.slice(0, 2048),
          agent: anchor.dataset.researchAgent as EventData["agent"] });
      }
    };
    let lastScroll = 0;
    const scroll = (event: globalThis.Event) => {
      activity();
      if (performance.now() - lastScroll > 1000) {
        this.emit("scroll", { region: regionFor(event.target) });
        lastScroll = performance.now();
      }
    };
    const visibility = () => {
      tick(); visible = document.visibilityState !== "hidden";
      this.emit("visibility_changed", { visible });
      if (visible) root.querySelectorAll<HTMLElement>("[data-research-kind]").forEach(element => {
        observer?.unobserve(element); observer?.observe(element);
      });
      if (!visible) void this.flush();
    };
    const focus = () => { tick(); focused = true; activity(); };
    const blur = () => { tick(); focused = false; pointerPresent = false; };
    const pagehide = () => { tick(); this.emit("question_left"); void this.flush(); };
    // Impressions require viewport intersection, rather than merely DOM insertion.
    const observer = typeof IntersectionObserver !== "undefined" ? new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting || !visible) continue;
        const element = entry.target as HTMLElement;
        const d = element.dataset;
        if (d.researchQuestion && d.researchQuestion !== this.context.questionId) continue;
        const identity = `${d.researchKind}:${d.researchItem}`;
        if (seen.has(identity)) continue;
        seen.add(identity);
        this.emit(d.researchKind!, {
          item_id: d.researchItem, request_id: d.researchRequest,
          agent: d.researchAgent as EventData["agent"], position: d.researchPosition ? Number(d.researchPosition) : undefined,
          text: d.researchKind === "suggestion_displayed" ? element.textContent?.slice(0, 2000) : undefined,
          url: element instanceof HTMLAnchorElement ? element.href.slice(0, 2048) : undefined,
        });
      }
    }, { threshold: 0.1 }) : null;
    const discover = () => {
      root.querySelectorAll<HTMLElement>('[data-research-kind="ai_message_displayed"]').forEach(message => {
        message.querySelectorAll<HTMLAnchorElement>("a[href]").forEach((anchor, index) => {
          if (anchor.dataset.researchKind) return;
          anchor.dataset.researchKind = "reference_displayed";
          anchor.dataset.researchRegion = "reference";
          anchor.dataset.researchItem = `${message.dataset.researchItem}:ref:${index}`;
          anchor.dataset.researchRequest = message.dataset.researchRequest;
          anchor.dataset.researchAgent = message.dataset.researchAgent;
          anchor.dataset.researchQuestion = message.dataset.researchQuestion;
        });
      });
      root.querySelectorAll<HTMLElement>("[data-research-kind]").forEach(element => {
        if (!observed.has(element)) { observed.add(element); observer?.observe(element); }
      });
    };
    const mutations = new MutationObserver(discover);
    mutations.observe(root, { childList: true, subtree: true });
    discover();
    root.addEventListener("pointermove", move);
    root.addEventListener("pointerleave", leave);
    root.addEventListener("click", click, true);
    root.addEventListener("keydown", activity);
    root.addEventListener("scroll", scroll, true);
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("focus", focus);
    window.addEventListener("blur", blur);
    window.addEventListener("pagehide", pagehide);
    this.emit("question_visible", { visible, viewport_width: window.innerWidth, viewport_height: window.innerHeight });
    const interval = setInterval(() => { tick(); void this.flush(); }, 5000);
    return () => {
      tick(); this.emit("question_left"); void this.flush(); clearInterval(interval);
      observer?.disconnect(); mutations.disconnect();
      root.removeEventListener("pointermove", move); root.removeEventListener("pointerleave", leave);
      root.removeEventListener("click", click, true); root.removeEventListener("keydown", activity);
      root.removeEventListener("scroll", scroll, true); document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("focus", focus); window.removeEventListener("blur", blur); window.removeEventListener("pagehide", pagehide);
    };
  }
}
