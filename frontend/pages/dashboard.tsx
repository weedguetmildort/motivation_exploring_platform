import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { getStudyFlow, type StudyFlowResponse } from "../lib/study";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [flow, setFlow] = useState<StudyFlowResponse | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getMe();
        const u = res.user

        if (!cancelled && !u.demographics_completed) {
          router.replace("/demographics");
          return;
        }

        if (!cancelled) setUser(u);

        try {
          const f = await getStudyFlow();
          if (!cancelled) setFlow(f);
        } catch {
          // Flow display is non-essential; the page still works without it.
        }
      } catch {
        if (!cancelled) router.replace("/login");
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => { cancelled = true; };
  }, [router]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading dashboard…</div>
      </div>
    );
  }

  if (!user) return null;

  async function onLogout() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="site-header">
        <div className="site-header-inner">
          <div>
            <h1 className="page-title">Dashboard</h1>
            <p className="page-subtitle">Welcome to the dashboard, {user.email}</p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/profile")}
              className="btn-primary"
            >
              Profile
            </button>
            <button
              onClick={onLogout}
              className="btn-secondary"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="page-container">
        {/* Participant's own progress through the study. Replaces the fixed
            "Quiz" tile — the flow is now base plus every variant, in an order
            assigned per participant. */}
        {flow && flow.total_steps > 0 && (
          <section className="mb-6 rounded-2xl border bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg 2xl:text-xl font-semibold">
                  {flow.finished ? "Study complete" : "Your progress"}
                </h2>
                <p className="text-sm text-gray-600">
                  {flow.finished
                    ? "You’ve finished every step. Thank you for participating."
                    : `Step ${flow.completed_count + 1} of ${flow.total_steps}`}
                </p>
              </div>

              {!flow.finished && (
                <button
                  onClick={() => {
                    const current = flow.steps.find(
                      (s) => s.id === flow.current_step_id,
                    );
                    router.push(current?.route ?? "/survey");
                  }}
                  className="btn-primary"
                >
                  Continue
                </button>
              )}
            </div>

            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-gray-100">
              <div
                className="h-full rounded-full bg-blue-600 transition-all"
                style={{
                  width: `${Math.round(
                    (flow.completed_count / flow.total_steps) * 100,
                  )}%`,
                }}
              />
            </div>

            <ol className="mt-4 space-y-1">
              {flow.steps.map((s) => {
                const isCurrent = s.id === flow.current_step_id;
                return (
                  <li
                    key={s.id}
                    className={[
                      "flex items-center gap-2 rounded-md px-2 py-1 text-sm",
                      isCurrent ? "bg-blue-50 font-medium text-blue-800" : "",
                      s.completed ? "text-gray-500" : "text-gray-700",
                    ].join(" ")}
                  >
                    <span aria-hidden="true">
                      {s.completed ? "✓" : isCurrent ? "→" : "•"}
                    </span>
                    <span className={s.completed ? "line-through" : ""}>
                      {s.label}
                    </span>
                  </li>
                );
              })}
            </ol>
          </section>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          {user?.is_admin && (
            <a
              href="/chat"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Chat</h2>
              <p className="text-sm text-gray-600">
                Ask questions and interact with AI chatbot
              </p>
            </a>
          )}
          
          {user?.is_admin && (
            <a
              href="/playground"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Playground</h2>
              <p className="text-sm text-gray-600">Sandbox to see how the different quiz styles look</p>
            </a>
          )}

          {user?.is_admin && (
            <a
              href="/admin"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Admin Panel</h2>
              <p className="text-sm text-gray-600">Manage questions and content</p>
            </a>
          )}
          {/* Participants reach their quizzes through the progress card above,
              which follows their assigned order. Admins keep direct links so
              they can open any variant out of sequence for testing. */}
          {user?.is_admin &&
            flow?.steps
              .filter((s) => s.kind === "quiz")
              .map((s) => (
                <a
                  key={s.id}
                  href={s.route}
                  className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
                >
                  <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">
                    {s.label}
                  </h2>
                  <p className="text-sm text-gray-600">
                    {s.completed ? "Completed — reopen" : "Begin the Quiz"}
                  </p>
                </a>
              ))}
        </div>
      </div>
    </div>
  );
}
