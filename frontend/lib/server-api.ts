import "server-only";

import { cookies } from "next/headers";

import {
  ApiError,
  apiBaseUrl,
  unwrap,
  type Health,
  type Passkey,
  type User,
} from "./api";
import type { Profile } from "./profile-api";

/**
 * Server-side calls to Django.
 *
 * A server component has no browser to attach cookies for it, so the incoming
 * request's cookies are forwarded by hand. Without this, every server-rendered
 * page would look logged out.
 */
async function serverFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const cookieStore = await cookies();
  const headers = new Headers(init.headers);
  const cookieHeader = cookieStore.toString();
  if (cookieHeader) headers.set("Cookie", cookieHeader);

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers,
    // Session-dependent responses must never be cached across users.
    cache: "no-store",
  });

  return unwrap<T>(response);
}

/** The signed-in user, or null when there is no valid session. */
export async function getCurrentUser(): Promise<User | null> {
  try {
    return await serverFetch<User>("/api/auth/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/** API liveness, or null when Django is unreachable. */
export async function getHealth(): Promise<Health | null> {
  try {
    return await serverFetch<Health>("/api/health");
  } catch {
    return null;
  }
}

/**
 * The signed-in member's own profile, or null when there is no valid session.
 *
 * Read on the server so the whole screen is in the first paint. That matters more here than it
 * would elsewhere: a profile form that arrives empty and fills in a moment later is a form a
 * member can start typing into before their own details land on top of what they typed.
 *
 * A 401 answers null rather than throwing, matching `getCurrentUser`. It cannot happen past the
 * club layout's guard, and the branch exists so a caller cannot forget it.
 */
export async function getProfile(): Promise<Profile | null> {
  try {
    return await serverFetch<Profile>("/api/accounts/me/profile");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/** The signed-in user's enrolled passkeys, or an empty list when signed out. */
export async function getPasskeys(): Promise<Passkey[]> {
  try {
    return await serverFetch<Passkey[]>("/api/auth/passkeys");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return [];
    throw error;
  }
}
