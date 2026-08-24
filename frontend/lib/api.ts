/**
 * The only module that knows how to reach the Django API.
 *
 * Safe to import from both server and client components. Anything that needs
 * request-scoped cookies lives in `lib/server-api.ts` instead, because
 * `next/headers` cannot be imported into client bundles.
 */

import type {
  AuthenticationResponseJSON,
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON,
  RegistrationResponseJSON,
} from "@simplewebauthn/browser";

/** Base URL used by server components and route handlers (container network). */
const SERVER_BASE_URL = process.env.DJANGO_API_URL ?? "http://localhost:8000";

/** Base URL used by the browser. Must be publicly reachable. */
const BROWSER_BASE_URL =
  process.env.NEXT_PUBLIC_DJANGO_API_URL ?? "http://localhost:8000";

export const apiBaseUrl = () =>
  typeof window === "undefined" ? SERVER_BASE_URL : BROWSER_BASE_URL;

/**
 * The signed-in member, mirroring UserOut in accounts/schemas.py.
 *
 * `id` is a UUID string, not a number. `email` and the names are nullable or
 * blank because an erased account keeps its row -- it can never sign in, so
 * this shape will not appear in practice, but the type has to admit it.
 * Prefer `display_name` for anything shown on screen.
 */
export type User = {
  id: string;
  email: string | null;
  first_name: string;
  last_name: string;
  nickname: string;
  /** `+27` and nine digits, or blank. A contact detail, not a credential. */
  mobile: string;
  display_name: string;
  /** ISO date, or null when none is on file. */
  date_of_birth: string | null;
  /**
   * ISO datetime. Null until someone checked it against a document -- which
   * registration does not do: a number that passes its check digit is a number
   * that is not a typo, and nobody has seen an ID.
   */
  date_of_birth_verified_at: string | null;
  /**
   * Only `active` can sign in. `pending_payment` is where registration leaves a
   * member until a payment lands; Django derives `is_active` from this and a
   * check constraint holds the two together, so this is reportable rather than
   * enforceable here.
   */
  status:
    | "pending"
    | "pending_payment"
    | "active"
    | "suspended"
    | "inactive"
    /**
     * A sharing member: an identity a cultivator registered to hold stock in
     * the swap zone. Never signs in -- it has no email address, and a check
     * constraint keeps the role out of `active` -- so this value cannot reach a
     * signed-in session. The contract admits it because the type describes the
     * column, not only what a browser will see.
     */
    | "sharing";
  /**
   * What the account is, as opposed to whether it may sign in. Registration
   * makes everybody a `member`; `admin` and `cultivator` are appointed in the
   * Django admin, and `sharing_member` is registered by a cultivator.
   * Independent of `is_staff`, which opens the Django admin and nothing else.
   *
   * A `sharing_member` never signs in and holds no permissions, so it will not
   * appear on a session -- see `status`.
   */
  role: "admin" | "cultivator" | "member" | "sharing_member";
  /**
   * Every `platform.*` action this account holds, sorted. Sent alongside
   * `role` so that nothing here has to map one to the other -- that map lives
   * in `accounts/roles.py`, and a copy of it in this bundle would drift from
   * the one the API enforces, showing up as a menu offering something the API
   * then refuses.
   *
   * For rendering, never for deciding. Empty for an account that is not
   * active, and the whole catalogue for a superuser. Every endpoint checks the
   * permission itself; this is a hint about what to draw.
   */
  permissions: string[];
  is_staff: boolean;
};

export type Health = {
  status: string;
  debug: boolean;
};

/** One enrolled WebAuthn credential, as the API reports it. */
export type Passkey = {
  id: number;
  name: string;
  /** True for a synced passkey (iCloud Keychain, Google Password Manager). */
  backed_up: boolean;
  device_type: string;
  created_at: string;
  last_used_at: string | null;
};

/** What `startLogin` came back with: which credential to collect next. */
export type LoginStart = {
  method: "passkey" | "otp";
  options: PublicKeyCredentialRequestOptionsJSON | null;
};

/** A non-2xx response from Django, carrying its status and message. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Turn a Django response into data, or throw an ApiError describing it. */
export async function unwrap<T>(response: Response): Promise<T> {
  const body = await response.text();
  const parsed = body ? safeJsonParse(body) : null;

  if (!response.ok) {
    // django-ninja reports errors as {"detail": "..."}.
    const detail =
      (parsed && typeof parsed === "object" && "detail" in parsed
        ? String((parsed as { detail: unknown }).detail)
        : null) ?? `Request failed with status ${response.status}`;
    throw new ApiError(response.status, detail);
  }

  return parsed as T;
}

function safeJsonParse(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

/* -------------------------------------------------------------------------- */
/* Browser-side calls                                                          */
/* -------------------------------------------------------------------------- */

function readCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${name}=([^;]*)`),
  );
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Return a CSRF token, asking Django to issue one if the cookie is missing.
 *
 * Django only sets `csrftoken` once something requests it, so a fresh visitor
 * has no token until this runs.
 */
export async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie("csrftoken");
  if (existing) return existing;

  await fetch(`${apiBaseUrl()}/api/auth/csrf`, { credentials: "include" });

  const issued = readCookie("csrftoken");
  if (!issued) {
    throw new ApiError(
      500,
      "Django did not issue a CSRF cookie. Check that the API origin is listed " +
        "in DJANGO_CORS_ALLOWED_ORIGINS and shares a hostname with this app.",
    );
  }
  return issued;
}

/** `fetch` against the API from the browser, with cookies and CSRF handled. */
export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);

  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    headers.set("X-CSRFToken", await ensureCsrfToken());
    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers,
    // Required: the session lives in a cookie on the Django origin.
    credentials: "include",
  });

  return unwrap<T>(response);
}

export const logout = () =>
  apiFetch<{ detail: string }>("/api/auth/logout", { method: "POST" });

/* -------------------------------------------------------------------------- */
/* Sign-in                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Ask Django which credential this address should be challenged for.
 *
 * `passkey` carries the WebAuthn request options. `otp` means a code has been
 * emailed — and is also what an unrecognised address gets back, so nothing
 * here tells the caller whether an account exists.
 */
export const startLogin = (email: string) =>
  apiFetch<LoginStart>("/api/auth/login/start", {
    method: "POST",
    body: JSON.stringify({ email }),
  });

export const loginWithPasskey = (
  email: string,
  credential: AuthenticationResponseJSON,
) =>
  apiFetch<User>("/api/auth/login/passkey", {
    method: "POST",
    body: JSON.stringify({ email, credential }),
  });

/** Send (or resend) an emailed sign-in code. Always resolves. */
export const sendLoginCode = (email: string) =>
  apiFetch<{ detail: string }>("/api/auth/otp/start", {
    method: "POST",
    body: JSON.stringify({ email }),
  });

export const loginWithCode = (email: string, code: string) =>
  apiFetch<User>("/api/auth/otp/verify", {
    method: "POST",
    body: JSON.stringify({ email, code }),
  });

/* -------------------------------------------------------------------------- */
/* Passkey management (requires a session)                                     */
/* -------------------------------------------------------------------------- */

export const passkeyRegistrationOptions = () =>
  apiFetch<{ options: PublicKeyCredentialCreationOptionsJSON }>(
    "/api/auth/passkeys/options",
    { method: "POST" },
  );

export const registerPasskey = (
  credential: RegistrationResponseJSON,
  name: string,
) =>
  apiFetch<Passkey>("/api/auth/passkeys", {
    method: "POST",
    body: JSON.stringify({ credential, name }),
  });

export const listPasskeys = () => apiFetch<Passkey[]>("/api/auth/passkeys");

export const deletePasskey = (id: number) =>
  apiFetch<{ detail: string }>(`/api/auth/passkeys/${id}`, {
    method: "DELETE",
  });
