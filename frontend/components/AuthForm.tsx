import { useState } from "react";
import { useRouter } from "next/router";
import { login, signup } from "../lib/auth";

type Props = {
  mode: "login" | "signup";
};

const MIN_PASSWORD_LENGTH = 6;

export default function AuthForm({ mode }: Props) {
  const router = useRouter();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [consent, setConsent] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const passwordTooShort =
    mode === "signup" &&
    password.length > 0 &&
    password.length < MIN_PASSWORD_LENGTH;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (pending) return;

    setError(null);

    if (mode === "signup") {
      if (!firstName.trim() || !lastName.trim()) {
        setError("First name and last name are required.");
        return;
      }

      if (password.length < MIN_PASSWORD_LENGTH) {
        setError(
          `Password must be at least ${MIN_PASSWORD_LENGTH} characters long.`,
        );
        return;
      }

      if (!consent) {
        setError("You must consent to participate in the study.");
        return;
      }
    }

    setPending(true);
    try {
      if (mode === "login") {
        await login(email.trim(), password);
        router.push("/dashboard");
      } else {
        await signup({
          firstName: firstName.trim(),
          lastName: lastName.trim(),
          email: email.trim(),
          password,
          consent,
        });
        router.push("/consent");
      }
    } catch (err: any) {
      setError(err?.message || "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="mx-auto mt-16 max-w-sm rounded-2xl border bg-white p-6 shadow-sm"
    >
      <h1 className="mb-4 text-xl font-semibold">
        {mode === "login" ? "Log in" : "Create an account"}
      </h1>

      {mode === "signup" && (
        <>
          <label className="mb-2 block text-sm font-medium">First Name</label>
          <input
            type="text"
            autoComplete="given-name"
            className="mb-4 w-full rounded-xl border px-3 py-2 focus:outline-none focus:ring"
            placeholder="John"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            required
          />

          <label className="mb-2 block text-sm font-medium">Last Name</label>
          <input
            type="text"
            autoComplete="family-name"
            className="mb-4 w-full rounded-xl border px-3 py-2 focus:outline-none focus:ring"
            placeholder="Doe"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            required
          />
        </>
      )}

      <label className="mb-2 block text-sm font-medium">Email</label>
      <input
        type="email"
        autoComplete="email"
        className="mb-4 w-full rounded-xl border px-3 py-2 focus:outline-none focus:ring"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />

      <label className="mb-2 block text-sm font-medium">Password</label>
      <input
        type="password"
        autoComplete={mode === "login" ? "current-password" : "new-password"}
        className="mb-4 w-full rounded-xl border px-3 py-2 focus:outline-none focus:ring"
        placeholder="••••••••"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        minLength={mode === "signup" ? MIN_PASSWORD_LENGTH : undefined}
        required
      />

      {mode === "signup" && (
        <p
          className={`mb-4 text-xs ${passwordTooShort ? "text-red-600" : "text-gray-500"}`}
        >
          Password must be at least {MIN_PASSWORD_LENGTH} characters.
        </p>
      )}

      {mode === "signup" && (
        <label className="mb-4 flex items-start gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            className="mt-1"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            required
          />
          <span>
            I consent to participate in this study and understand that my
            information will be used for research purposes.
          </span>
        </label>
      )}

      {error && (
        <div role="alert" className="mb-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={pending}
        className="w-full rounded-xl bg-blue-600 px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        {pending ? "Please wait…" : mode === "login" ? "Log in" : "Sign up"}
      </button>

      <p className="mt-4 text-center text-sm text-gray-600">
        {mode === "login" ? (
          <>
            Don&apos;t have an account?{" "}
            <a className="text-blue-600 underline" href="/signup">
              Sign up
            </a>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <a className="text-blue-600 underline" href="/login">
              Log in
            </a>
          </>
        )}
      </p>
    </form>
  );
}