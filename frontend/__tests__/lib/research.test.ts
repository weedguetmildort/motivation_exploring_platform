import { QuestionResearch, regionFor } from "../../lib/research";

let impressions: IntersectionObserverCallback;
const observed: Element[] = [];
class Observer {
  constructor(callback: IntersectionObserverCallback) { impressions = callback; }
  observe(element: Element) { observed.push(element); }
  unobserve() {}
  disconnect() {}
}
let student = 0;
function setup() {
  const root = document.createElement("div");
  root.innerHTML = '<section data-research-region="question"><button>Answer</button></section><section data-research-region="chat"><p data-research-kind="ai_message_displayed" data-research-item="r:default" data-research-request="r" data-research-agent="default" data-research-question="q"><a href="https://example.edu/source">Source</a></p></section>';
  document.body.appendChild(root);
  const tracker = new QuestionResearch({ userId: `student-${++student}`, questionId: "q", conversationId: "c" });
  const stop = tracker.start(root);
  return { root, tracker, stop };
}
function sentEvents() {
  return (global.fetch as jest.Mock).mock.calls.flatMap(([, init]) => JSON.parse(init.body).events);
}
beforeEach(() => {
  jest.useFakeTimers();
  localStorage.clear(); observed.length = 0;
  global.fetch = jest.fn().mockResolvedValue({ ok: true });
  Object.defineProperty(global, "IntersectionObserver", { configurable: true, writable: true, value: Observer });
  jest.spyOn(document, "hasFocus").mockReturnValue(true);
  jest.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
});
afterEach(() => { jest.restoreAllMocks(); jest.useRealTimers(); document.body.innerHTML = ""; });

test("records pointer region dwell separately from clicks and active time", async () => {
  const { root, tracker, stop } = setup();
  const pointer = new MouseEvent("pointermove", { bubbles: true });
  Object.defineProperty(pointer, "pointerType", { value: "mouse" });
  root.querySelector("p")!.dispatchEvent(pointer);
  jest.advanceTimersByTime(5000);
  await tracker.flush();
  const interval = sentEvents().find(event => event.event_type === "activity_interval");
  expect(interval.data).toEqual(expect.objectContaining({ region: "chat", pointer_ms: 5000, active_ms: 5000, visible_ms: 5000 }));
  expect(regionFor(root.querySelector("button"))).toBe("question");
  stop(); await tracker.flush();
});

test("impressions are deduplicated and reference clicks identify the shown message", async () => {
  const { root, tracker, stop } = setup();
  const entries = observed.map(target => ({ target, isIntersecting: true } as IntersectionObserverEntry));
  impressions(entries, {} as IntersectionObserver);
  impressions(entries, {} as IntersectionObserver);
  root.querySelector("a")!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  await tracker.flush();
  const events = sentEvents();
  expect(events.filter(event => event.event_type === "reference_displayed")).toHaveLength(1);
  expect(events.filter(event => event.event_type === "ai_message_displayed")).toHaveLength(1);
  expect(events.find(event => event.event_type === "reference_clicked").data).toEqual(expect.objectContaining({ request_id: "r", item_id: "r:default:ref:0", url: "https://example.edu/source" }));
  stop(); await tracker.flush();
});

test("a failed delivery retries the same event IDs", async () => {
  const { tracker, stop } = setup();
  (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: false });
  await tracker.flush();
  const first = JSON.parse((global.fetch as jest.Mock).mock.calls[0][1].body).events;
  await tracker.flush();
  const second = JSON.parse((global.fetch as jest.Mock).mock.calls[1][1].body).events;
  expect(second.map((event: { event_id: string }) => event.event_id)).toEqual(first.map((event: { event_id: string }) => event.event_id));
  stop(); await tracker.flush();
});

describe("a batch the server rejects as invalid", () => {
  // The server validates whole batches: one malformed event rejects the rest.
  function rejecting(status: number, isBad = (event: { event_type: string }) => event.event_type === "bad") {
    global.fetch = jest.fn((_: unknown, init: { body: string }) => {
      const events = JSON.parse(init.body).events;
      return Promise.resolve(events.some(isBad) ? { ok: false, status } : { ok: true, status: 200 });
    }) as jest.Mock;
  }
  function tracker() {
    return new QuestionResearch({ userId: `student-${++student}`, questionId: "q", conversationId: "c" });
  }
  const batches = () => (global.fetch as jest.Mock).mock.calls.map(([, init]) => JSON.parse(init.body).events);

  test.each([400, 413, 422])("a %i drops only the malformed event and delivers the rest", async status => {
    rejecting(status);
    const research = tracker();
    research.emit("first"); research.emit("bad"); research.emit("last");
    await research.flush();
    const accepted = batches().filter(events => !events.some((event: { event_type: string }) => event.event_type === "bad"));
    expect(accepted.flat().map((event: { event_type: string }) => event.event_type)).toEqual(["first", "last"]);
    (global.fetch as jest.Mock).mockClear();
    await research.flush();
    expect(global.fetch).not.toHaveBeenCalled(); // nothing is left to resend
    expect(Object.keys(localStorage).filter(key => key.startsWith("mep.research"))).toEqual([]);
  });

  test("later events are not blocked behind the malformed one", async () => {
    rejecting(422);
    const research = tracker();
    research.emit("bad");
    for (let index = 0; index < 60; index++) research.emit(`good-${index}`);
    await research.flush();
    const sent = batches();
    // One rejected batch of 50, its 50 events singly, then the other 11 batched again.
    expect(sent.map(events => events.length)).toEqual([50, ...Array(50).fill(1), 11]);
    expect(sent.slice(1).flat().filter((event: { event_type: string }) => event.event_type !== "bad")).toHaveLength(60);
  });

  test.each([401, 403, 429, 500, 503])("a %i keeps every event for a later retry", async status => {
    rejecting(status, () => true);
    const research = tracker();
    research.emit("first"); research.emit("second");
    await research.flush();
    await research.flush();
    const sent = batches();
    expect(sent).toHaveLength(2);
    expect(sent[1].map((event: { event_id: string }) => event.event_id)).toEqual(sent[0].map((event: { event_id: string }) => event.event_id));
    expect(sent[0]).toHaveLength(2);
  });

  test("a network failure while isolating keeps the remaining events", async () => {
    let calls = 0;
    global.fetch = jest.fn((_: unknown, init: { body: string }) => {
      calls += 1;
      if (calls === 1) return Promise.resolve({ ok: false, status: 422 });
      if (calls === 2) return Promise.reject(new TypeError("offline"));
      return Promise.resolve({ ok: true, status: 200 });
    }) as jest.Mock;
    const research = tracker();
    research.emit("first"); research.emit("second");
    await research.flush();
    expect(batches()[1]).toHaveLength(1); // isolation had started when the network dropped
    await research.flush();
    // After reconnecting, a fresh flush batches normally and delivers both.
    expect(batches()[2].map((event: { event_type: string }) => event.event_type)).toEqual(["first", "second"]);
    (global.fetch as jest.Mock).mockClear();
    await research.flush();
    expect(global.fetch).not.toHaveBeenCalled();
  });
});

test("hidden and unfocused intervals do not count as pointer or active engagement", async () => {
  const { root, tracker, stop } = setup();
  const pointer = new MouseEvent("pointermove", { bubbles: true });
  Object.defineProperty(pointer, "pointerType", { value: "mouse" });
  root.querySelector("p")!.dispatchEvent(pointer);
  window.dispatchEvent(new Event("blur"));
  jest.advanceTimersByTime(5000);
  await tracker.flush();
  const interval = sentEvents().find(event => event.event_type === "activity_interval");
  expect(interval.data.pointer_ms).toBe(0);
  expect(interval.data.active_ms).toBe(0);
  stop(); await tracker.flush();
});

test("recommendations from a previous question are not current-question impressions", async () => {
  const { root, tracker, stop } = setup();
  root.querySelector<HTMLElement>("p")!.dataset.researchQuestion = "old-question";
  root.querySelector<HTMLElement>("a")!.dataset.researchQuestion = "old-question";
  impressions(observed.map(target => ({ target, isIntersecting: true } as IntersectionObserverEntry)), {} as IntersectionObserver);
  await tracker.flush();
  expect(sentEvents().some(event => event.event_type === "ai_message_displayed")).toBe(false);
  stop(); await tracker.flush();
});


test("queued events keep their originating study when selection changes", async () => {
  window.history.replaceState({}, "", "/dashboard?study=study-2");
  const { tracker, stop } = setup();
  window.history.replaceState({}, "", "/dashboard?study=study-1");
  await tracker.flush();
  expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe("/api/studies/study-2/research/events");
  stop(); await tracker.flush();
  sessionStorage.clear();
});
