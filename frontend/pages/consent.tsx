import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout } from "../lib/auth";

export default function ConsentPage() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        await getMe();
      } catch {
        if (!cancelled) {
          router.replace("/login");
          return;
        }
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }

  async function onAgree() {
    if (pending) return;
    setPending(true);
    router.push("/dashboard");
  }

  async function onDecline() {
    if (pending) return;
    setPending(true);
    try {
      await logout();
    } catch {
      // Ignore — still navigate away below regardless of logout outcome.
    } finally {
      router.replace("/login");
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-2xl rounded-2xl border bg-white p-6 shadow-sm">
        <h1 className="mb-4 text-xl font-semibold">Research Consent Form</h1>

        <div className="mb-4 space-y-1 text-sm text-gray-700">
          <p>
            <span className="font-medium">Title of Project:</span> Understanding
            Overreliance towards AI in Educational Settings
          </p>
          <p>
            <span className="font-medium">Principal Investigator:</span> Neha
            Rani (Faculty in CISE) —{" "}
            <a className="underline" href="mailto:neharani@ufl.edu">
              neharani@ufl.edu
            </a>
          </p>
        </div>

        <div className="space-y-4 text-sm text-gray-700">
          <p>
            Please read the information below carefully before you decide to
            participate in this research study. Your participation is
            voluntary. You can decide not to participate or later decide to
            stop participating at any time without penalty or lose any
            benefits that would normally be expected.
          </p>

          <section>
            <h2 className="font-semibold text-gray-900">Purpose of the Study</h2>
            <p className="mt-1">
              The purpose of this research study is to understand students&apos;
              overreliance on AI in educational settings.
            </p>
          </section>

          <section>
            <h2 className="font-semibold text-gray-900">
              What will you be asked to do
            </h2>
            <p className="mt-1">
              If you agree to take part in this study, you will be engaged in
              an online study. You will be asked to fill out questionnaires
              asking about your demographics and your experience with AI
              tools. You will be asked to answer a few mathematics questions,
              specifically statistics, permutations, and combinations. You
              will also have an AI chat assistant to help you with
              problem-solving. You will be asked to fill out a post survey as
              well.
            </p>
          </section>

          <p>
            If you have any questions now or at any time during the study,
            please contact the Principal Investigator listed above.
          </p>

          <section>
            <h2 className="font-semibold text-gray-900">Time Required</h2>
            <p className="mt-1">
              It will take about 45 minutes to participate in the research.
            </p>
          </section>

          <section>
            <h2 className="font-semibold text-gray-900">Research Benefits</h2>
            <p className="mt-1">
              There are no direct benefits to you for being in this study.
              There may be a benefit to others depending on the results of
              this study.
            </p>
          </section>

          <section>
            <h2 className="font-semibold text-gray-900">Research Risks</h2>
            <p className="mt-1">
              There are no known risks beyond those normally encountered in
              daily life (loss of time, boredom) for a participant. There are
              no direct benefits of study participation.
            </p>
          </section>

          <section>
            <h2 className="font-semibold text-gray-900">
              Statement of Confidentiality
            </h2>
            <p className="mt-1">
              Your participation in this research is confidential.
              Information collected about you will be stored in computers
              with security passwords or in locked filing cabinets. Only
              certain people have the legal right to review these research
              records, and they will protect the secrecy (confidentiality) of
              these records as much as the law allows. These people include
              the researchers for this study, certain University of Florida
              officials, and the Institutional Review Board (IRB; an IRB is a
              group of people who are responsible for looking after the
              rights and welfare of people taking part in research).
              Otherwise your research records will not be released without
              your permission unless required by law or a court order. The
              researchers will not share your name or other identifiable
              information about you if they publish, present, or share the
              results this research.
            </p>
          </section>

          <section>
            <h2 className="font-semibold text-gray-900">
              Who to contact if you have questions
            </h2>
            <p className="mt-1">
              Please contact Neha Rani at (352) 871 5080 with questions or
              concerns about this study.
            </p>
          </section>

          <section>
            <h2 className="font-semibold text-gray-900">
              Voluntary Participation
            </h2>
            <p className="mt-1">
              Your decision to be in this research is voluntary. You do not
              have to do any study activities that you do not want to take
              part in. You can stop at any time. If you decide you want to
              stop participating in the research, you can let the research
              team know or call the Principal Investigator at any time at
              (352) 871 5080. If you choose not to take part, this will have
              no effect on you or your relationships with the University of
              Florida. If you have any questions about your rights as a
              research subject, you can phone the Institutional Review Board
              at 352-273-9600.
            </p>
          </section>

          <p>
            Participation in the research implies that you have read the
            information in this form and consent to take part in the
            research. Please save a copy of this form for your records or
            future reference.
          </p>
        </div>

        <div className="mt-6 border-t pt-4">
          <p className="mb-4 text-sm text-gray-700">
            If you want to participate in this research study, click the{" "}
            <span className="font-medium">&quot;I agree to participate&quot;</span>{" "}
            button below. If you do not want to participate, you may simply
            close this window or click{" "}
            <span className="font-medium">
              &quot;I do not wish to participate&quot;
            </span>
            .
          </p>

          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={onAgree}
              disabled={pending}
              className="flex-1 rounded-xl bg-blue-600 px-4 py-2 font-medium text-white disabled:opacity-60"
            >
              I agree to participate
            </button>
            <button
              type="button"
              onClick={onDecline}
              disabled={pending}
              className="flex-1 rounded-xl border px-4 py-2 font-medium text-gray-700 disabled:opacity-60"
            >
              I do not wish to participate
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
