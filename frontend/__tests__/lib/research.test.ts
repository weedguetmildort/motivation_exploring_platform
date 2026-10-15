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
