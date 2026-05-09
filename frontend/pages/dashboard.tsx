import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { buildStudySteps } from "../lib/studySteps";
import ProgressBar from "../components/ProgressBar";
import PageHeader from "../components/PageHeader";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getMe();
        const u = res.user;
        if (!cancelled && !u.demographics_completed) {
          router.replace("/demographics");
          return;
        }
        if (!cancelled) setUser(u);
      } catch {
        if (!cancelled) router.replace("/login");
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

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

  const steps = buildStudySteps(user);
  const nextStep = steps.find((s) => !s.completed && s.path);
  const allComplete = steps.every((s) => s.completed);
  const actionVerb = user.survey_pre_base_completed ? "Continue" : "Start";

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Dashboard"
        subtitle="Study progress overview."
        onProfile={() => router.push("/profile")}
        onLogout={onLogout}
      />

      <div className="page-container flex flex-col gap-4">
        <ProgressBar user={user} horizontal />

        {/* ── Next Step Hero Card ── */}
        {allComplete ? (
          <div className="w-full rounded-2xl border-2 border-blue-200 bg-blue-50 p-6 text-center shadow-sm">
            <p className="text-xl font-semibold text-blue-800">Study Complete — thank you for participating!</p>
          </div>
        ) : nextStep ? (
          <div className="w-full rounded-2xl border-2 border-blue-500 bg-white shadow-md overflow-hidden">
            <div className="bg-blue-600 px-6 py-4">
              <p className="text-xs font-semibold uppercase tracking-widest text-blue-200 mb-1">Next Step</p>
              <h2 className="text-2xl font-bold text-white">{nextStep.label}</h2>
              <p className="mt-1 text-sm text-blue-100">{nextStep.subtitle}</p>
            </div>
            <div className="px-6 py-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Estimated time: <span className="font-medium text-gray-700">{nextStep.time}</span>
              </div>
              <button
                onClick={() => router.push(nextStep.path)}
                className="w-full sm:w-auto rounded-xl bg-blue-600 px-8 py-3 text-base font-semibold text-white shadow hover:bg-blue-700 active:scale-[0.98] transition-all"
              >
                {actionVerb} the {nextStep.label}
              </button>
            </div>
          </div>
        ) : null}

        {/* ── Admin Section ── */}
        {user.is_admin && (
          <>
            <div className="relative mt-2">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-300" />
              </div>
              <div className="relative flex justify-start">
                <span className="bg-gray-50 pr-3 text-xs font-semibold uppercase tracking-widest text-gray-400">Admin</span>
              </div>
            </div>

            {/* Tools */}
            <div className="grid gap-4 sm:grid-cols-3">
              {([
                {
                  href: "/chat",
                  label: "Chat",
                  desc: "Ask questions and interact with AI",
                  icon: <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />,
                },
                {
                  href: "/playground",
                  label: "Playground",
                  desc: "Preview and compare quiz styles",
                  icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />,
                },
                {
                  href: "/admin",
                  label: "Admin Panel",
                  desc: "Manage questions and content",
                  icon: <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" />,
                },
              ] as const).map((tool) => (
                <a key={tool.href} href={tool.href}
                  className="group flex items-center gap-5 rounded-2xl border bg-white p-5 shadow-sm hover:border-blue-300 hover:shadow-md transition-all"
                >
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600 group-hover:bg-blue-100 transition-colors">
                    <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>{tool.icon}</svg>
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 leading-tight">{tool.label}</h2>
                    <p className="text-sm text-gray-500 mt-0.5">{tool.desc}</p>
                  </div>
                </a>
              ))}
            </div>

            {/* Study flow separator */}
            <div className="relative mt-1">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200" />
              </div>
              <div className="relative flex justify-start">
                <span className="bg-gray-50 pr-3 text-xs font-medium uppercase tracking-widest text-gray-400">Study Flow</span>
              </div>
            </div>

            {/* Quizzes */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {([
                { href: "/quiz/base",     label: "Base Quiz",           theme: "base" },
                { href: "/quiz/followup", label: "Follow-Up Questions", theme: "followup" },
                { href: "/quiz/double",   label: "Dual Agent",          theme: "double" },
                { href: "/quiz/links",    label: "Embedded Links",      theme: "links" },
              ] as const).map((q) => (
                <a key={q.href} href={q.href} data-quiz-theme={q.theme}
                  className="group flex items-center gap-4 rounded-2xl border bg-white p-5 shadow-sm hover:border-accent-400 hover:shadow-md transition-all"
                >
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-accent-50 text-accent-600 group-hover:bg-accent-100 transition-colors">
                    <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 leading-tight">{q.label}</h2>
                    <p className="text-sm text-gray-500 mt-0.5">Quiz · 10 min</p>
                  </div>
                </a>
              ))}
            </div>

            {/* Surveys */}
            <div className="grid gap-4 sm:grid-cols-3">
              {([
                { href: "/survey?stage=pre_quiz",     label: "Pre-Quiz Survey", desc: "Before the base quiz · 5 min" },
                { href: "/survey?stage=post_base",    label: "Mid Survey",      desc: "After the base quiz · 5 min" },
                { href: "/survey?stage=post_variant", label: "Final Survey",    desc: "After the variant quiz · 5 min" },
              ] as const).map((s) => (
                <a key={s.href} href={s.href}
                  className="group flex items-center gap-4 rounded-2xl border bg-white p-5 shadow-sm hover:border-blue-300 hover:shadow-md transition-all"
                >
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-500 group-hover:bg-blue-100 transition-colors">
                    <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 leading-tight">{s.label}</h2>
                    <p className="text-sm text-gray-500 mt-0.5">{s.desc}</p>
                  </div>
                </a>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
