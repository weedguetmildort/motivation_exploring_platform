import { fetchStudyCatalog, invalidateStudyCatalog } from "../../lib/studyCatalog";
import { apiFetch } from "../../lib/fetcher";
jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));
beforeEach(() => { invalidateStudyCatalog(); jest.useRealTimers(); });

test("concurrent callers share one in-flight catalog request", async () => {
  let resolve!: (value: unknown) => void;
  (apiFetch as jest.Mock).mockReturnValueOnce(new Promise(r => { resolve = r; }));
  const first = fetchStudyCatalog(), second = fetchStudyCatalog();
  resolve({ studies: [] });
  expect(await first).toBe(await second);
  expect(apiFetch).toHaveBeenCalledTimes(1);
});

test("a just-finished result is reused, then refreshed once stale", async () => {
  jest.useFakeTimers({ now: 0 });
  (apiFetch as jest.Mock).mockReset().mockResolvedValueOnce({ studies: ["old"] }).mockResolvedValueOnce({ studies: ["new"] });
  expect((await fetchStudyCatalog()).studies).toEqual(["old"]);
  jest.setSystemTime(1500);
  expect((await fetchStudyCatalog()).studies).toEqual(["old"]);
  jest.setSystemTime(2500);
  expect((await fetchStudyCatalog()).studies).toEqual(["new"]);
  expect(apiFetch).toHaveBeenCalledTimes(2);
});

test("invalidation forces a fresh read after an access change", async () => {
  (apiFetch as jest.Mock).mockReset().mockResolvedValueOnce({ studies: ["locked"] }).mockResolvedValueOnce({ studies: ["unlocked"] });
  await fetchStudyCatalog();
  invalidateStudyCatalog();
  expect((await fetchStudyCatalog()).studies).toEqual(["unlocked"]);
});

test("a request sent before an access change answers with a fresh read", async () => {
  let resolveOld!: (value: unknown) => void;
  (apiFetch as jest.Mock).mockReset()
    .mockReturnValueOnce(new Promise(r => { resolveOld = r; }))
    .mockResolvedValueOnce({ studies: ["unlocked"] });
  const poll = fetchStudyCatalog(); // e.g. the 15 s poll, still waiting
  invalidateStudyCatalog();         // e.g. a code was just redeemed
  resolveOld({ studies: ["locked"] });
  expect((await poll).studies).toEqual(["unlocked"]);
  expect(apiFetch).toHaveBeenCalledTimes(2);
});

test("a stale answer is never cached for later callers", async () => {
  let resolveOld!: (value: unknown) => void;
  (apiFetch as jest.Mock).mockReset()
    .mockReturnValueOnce(new Promise(r => { resolveOld = r; }))
    .mockResolvedValueOnce({ studies: ["unlocked"] });
  const poll = fetchStudyCatalog();
  invalidateStudyCatalog();
  resolveOld({ studies: ["locked"] });
  await poll;
  expect((await fetchStudyCatalog()).studies).toEqual(["unlocked"]);
  expect(apiFetch).toHaveBeenCalledTimes(2);
});

test("callers after an invalidation share the fresh request", async () => {
  let resolveOld!: (value: unknown) => void;
  let resolveNew!: (value: unknown) => void;
  (apiFetch as jest.Mock).mockReset()
    .mockReturnValueOnce(new Promise(r => { resolveOld = r; }))
    .mockReturnValueOnce(new Promise(r => { resolveNew = r; }));
  const stale = fetchStudyCatalog();
  invalidateStudyCatalog();
  const fresh = fetchStudyCatalog();
  resolveOld({ studies: ["locked"] });
  resolveNew({ studies: ["unlocked"] });
  expect((await stale).studies).toEqual(["unlocked"]);
  expect((await fresh).studies).toEqual(["unlocked"]);
  expect(apiFetch).toHaveBeenCalledTimes(2);
});

test("a failed request is not cached", async () => {
  (apiFetch as jest.Mock).mockReset().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ studies: [] });
  await expect(fetchStudyCatalog()).rejects.toThrow("offline");
  await expect(fetchStudyCatalog()).resolves.toEqual({ studies: [] });
});
