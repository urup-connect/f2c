"use client";

import {
  browserSupportsWebAuthn,
  startRegistration,
} from "@simplewebauthn/browser";
import { useState } from "react";

import {
  ApiError,
  deletePasskey,
  listPasskeys,
  passkeyRegistrationOptions,
  registerPasskey,
  type Passkey,
} from "@/lib/api";

function formatDate(value: string | null): string {
  if (!value) return "Never";
  return new Date(value).toLocaleDateString("en-ZA", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * A sensible default label, so a member who does not name their passkey still
 * ends up with a list they can tell apart later.
 */
function suggestName(): string {
  const agent = navigator.userAgent;
  if (/iPhone|iPad/.test(agent)) return "iPhone or iPad";
  if (/Android/.test(agent)) return "Android device";
  if (/Macintosh/.test(agent)) return "Mac";
  if (/Windows/.test(agent)) return "Windows PC";
  return "This device";
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.name === "NotAllowedError") {
    return "Passkey setup was cancelled.";
  }
  if (error instanceof Error && error.name === "InvalidStateError") {
    return "This device already has a passkey for your account.";
  }
  return "Could not set up a passkey on this device.";
}

export function PasskeyManager({ initial }: { initial: Passkey[] }) {
  const [passkeys, setPasskeys] = useState(initial);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const supported = typeof window !== "undefined" && browserSupportsWebAuthn();

  async function handleAdd() {
    setError(null);
    setIsBusy(true);
    try {
      const { options } = await passkeyRegistrationOptions();
      const credential = await startRegistration({ optionsJSON: options });
      await registerPasskey(credential, name.trim() || suggestName());
      // Re-read rather than appending: the server owns the canonical list.
      setPasskeys(await listPasskeys());
      setName("");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRemove(id: number) {
    setError(null);
    setIsBusy(true);
    try {
      await deletePasskey(id);
      setPasskeys((current) => current.filter((passkey) => passkey.id !== id));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {passkeys.length === 0 ? (
        <p className="rounded-lg border border-dashed border-neutral-300 px-5 py-4 text-sm text-neutral-600 dark:border-neutral-700 dark:text-neutral-400">
          You have no passkeys yet. Until you add one, every sign-in needs a
          code emailed to you.
        </p>
      ) : (
        <ul className="divide-y divide-neutral-200 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
          {passkeys.map((passkey) => (
            <li
              key={passkey.id}
              className="flex items-center justify-between gap-4 px-5 py-3 text-sm"
            >
              <div className="space-y-0.5">
                <p className="font-medium">
                  {passkey.name}
                  {passkey.backed_up && (
                    <span className="ml-2 rounded-full bg-neutral-100 px-2 py-0.5 text-xs font-normal text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
                      Synced
                    </span>
                  )}
                </p>
                <p className="text-xs text-neutral-500">
                  Added {formatDate(passkey.created_at)} · Last used{" "}
                  {formatDate(passkey.last_used_at)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => handleRemove(passkey.id)}
                disabled={isBusy}
                className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p
          role="alert"
          className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300"
        >
          {error}
        </p>
      )}

      {supported ? (
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            aria-label="Passkey name"
            placeholder="Name this device (optional)"
            value={name}
            onChange={(event) => setName(event.target.value.slice(0, 64))}
            className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-neutral-900 dark:border-neutral-700 dark:bg-neutral-900 dark:focus:border-neutral-100 sm:max-w-xs"
          />
          <button
            type="button"
            onClick={handleAdd}
            disabled={isBusy}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
          >
            {isBusy ? "Working…" : "Add a passkey"}
          </button>
        </div>
      ) : (
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          This browser cannot create passkeys. Sign in here with an emailed code
          and add a passkey from a browser that supports them.
        </p>
      )}
    </div>
  );
}
