"use client";

import {
  browserSupportsWebAuthn,
  startAuthentication,
} from "@simplewebauthn/browser";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  loginWithCode,
  loginWithPasskey,
  sendLoginCode,
  startLogin,
} from "@/lib/api";

/** Seconds to wait before another code can be requested. */
const RESEND_COOLDOWN = 30;

const inputClass =
  "w-full rounded-md border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-neutral-900 dark:border-neutral-700 dark:bg-neutral-900 dark:focus:border-neutral-100";

const primaryButtonClass =
  "w-full rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300";

const linkButtonClass =
  "text-sm text-neutral-600 underline underline-offset-4 hover:text-neutral-900 disabled:opacity-50 dark:text-neutral-400 dark:hover:text-neutral-100";

/**
 * Translate a failed WebAuthn ceremony into something a member can act on.
 *
 * The browser deliberately gives the same `NotAllowedError` whether the user
 * dismissed the prompt or no credential matched, so this cannot distinguish
 * the two — hence the wording, which covers both.
 */
function passkeyMessage(error: unknown): string {
  const name = error instanceof Error ? error.name : "";
  if (name === "NotAllowedError") {
    return "Passkey sign-in was cancelled, or no passkey on this device matched.";
  }
  if (name === "InvalidStateError") {
    return "This device's passkey is not registered to that account.";
  }
  if (name === "SecurityError") {
    return "Passkeys need a secure connection. Sign in at localhost or over HTTPS.";
  }
  return "Passkey sign-in did not complete on this device.";
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Could not reach the server. Please try again.";
}

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Set when a passkey attempt failed, so the fallback is offered explicitly
  // rather than silently swapping the form out from under the user.
  const [passkeyFailed, setPasskeyFailed] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const finish = useCallback(() => {
    // Only relative paths, so a crafted ?next= cannot redirect off-site.
    const next = searchParams.get("next");
    const destination =
      next && next.startsWith("/") && !next.startsWith("//")
        ? next
        : "/dashboard";
    // Refresh first so server components pick up the new session cookie.
    router.refresh();
    router.push(destination);
  }, [router, searchParams]);

  /** Move to the code step, sending a code first unless one is already out. */
  async function goToCodeStep(alreadySent: boolean) {
    if (!alreadySent) await sendLoginCode(email);
    setPasskeyFailed(false);
    setError(null);
    setNotice(`If ${email} belongs to a member, a code is on its way.`);
    setCooldown(RESEND_COOLDOWN);
    setStep("code");
  }

  /**
   * Identify the address, then collect whichever credential Django asks for.
   *
   * A passkey challenge is attempted immediately; anything else — including an
   * unrecognised address — lands on the code step, which is what keeps the two
   * cases indistinguishable from the outside.
   */
  async function handleEmailSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setIsBusy(true);

    try {
      const start = await startLogin(email);

      if (start.method === "passkey" && start.options) {
        if (!browserSupportsWebAuthn()) {
          // Django prepared a challenge this browser cannot answer, and so
          // sent no code. Ask for one now.
          await goToCodeStep(false);
          return;
        }
        try {
          const credential = await startAuthentication({
            optionsJSON: start.options,
          });
          await loginWithPasskey(email, credential);
          finish();
          return;
        } catch (caught) {
          // A cancelled or unmatched passkey is not a dead end.
          setError(passkeyMessage(caught));
          setPasskeyFailed(true);
          return;
        }
      }

      // login/start already emailed the code.
      await goToCodeStep(true);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCodeSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setIsBusy(true);

    try {
      await loginWithCode(email, code);
      finish();
    } catch (caught) {
      setError(errorMessage(caught));
      setIsBusy(false);
    }
  }

  async function handleSendCode() {
    setError(null);
    setIsBusy(true);
    try {
      await goToCodeStep(false);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsBusy(false);
    }
  }

  function handleStartOver() {
    setStep("email");
    setCode("");
    setError(null);
    setNotice(null);
    setPasskeyFailed(false);
  }

  const feedback = (
    <>
      {error && (
        <p
          role="alert"
          className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300"
        >
          {error}
        </p>
      )}
      {notice && (
        <p
          role="status"
          className="rounded-md bg-neutral-100 px-3 py-2 text-sm text-neutral-700 dark:bg-neutral-900 dark:text-neutral-300"
        >
          {notice}
        </p>
      )}
    </>
  );

  if (step === "code") {
    return (
      <form onSubmit={handleCodeSubmit} className="space-y-4">
        <div className="space-y-1">
          <label htmlFor="code" className="block text-sm font-medium">
            Sign-in code
          </label>
          <input
            id="code"
            name="code"
            value={code}
            onChange={(event) =>
              setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
            }
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="\d{6}"
            required
            autoFocus
            className={`${inputClass} tracking-[0.4em]`}
          />
          <p className="text-xs text-neutral-500">
            Six digits, sent to {email}. Valid for five minutes.
          </p>
        </div>

        {feedback}

        <button type="submit" disabled={isBusy} className={primaryButtonClass}>
          {isBusy ? "Checking…" : "Sign in"}
        </button>

        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={handleSendCode}
            disabled={isBusy || cooldown > 0}
            className={linkButtonClass}
          >
            {cooldown > 0 ? `Send a new code in ${cooldown}s` : "Send a new code"}
          </button>
          <button
            type="button"
            onClick={handleStartOver}
            disabled={isBusy}
            className={linkButtonClass}
          >
            Use a different address
          </button>
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={handleEmailSubmit} className="space-y-4">
      <div className="space-y-1">
        <label htmlFor="email" className="block text-sm font-medium">
          Email address
        </label>
        <input
          id="email"
          name="email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          // Lets the browser offer a saved passkey inline where it can.
          autoComplete="username webauthn"
          required
          autoFocus
          className={inputClass}
        />
      </div>

      {feedback}

      <button type="submit" disabled={isBusy} className={primaryButtonClass}>
        {isBusy ? "Checking…" : "Continue"}
      </button>

      <div className="text-center">
        <button
          type="button"
          onClick={handleSendCode}
          disabled={isBusy || !email}
          className={linkButtonClass}
        >
          {passkeyFailed ? "Email me a code instead" : "Email me a code"}
        </button>
      </div>
    </form>
  );
}
