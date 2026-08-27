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
import type { Member, MemberRow } from "./member-register";
import type { Profile } from "./profile-api";
import type {
  Cultivator,
  Strain,
  StrainRow,
  Vocabularies,
} from "./strain-catalogue";

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

/* -------------------------------------------------------------------------- */
/* The strain catalogue                                                        */
/* -------------------------------------------------------------------------- */

/*
 * Read on the server so the whole screen is in the first paint, for the reason
 * `getProfile` gives: a form that arrives empty and fills in a moment later is a
 * form an administrator can start typing into before the record lands on top of
 * what they typed. It matters more here than on the profile, because this form
 * has twenty fields and three of them are lists.
 *
 * These are `null`-on-403 rather than `null`-on-401, which is the difference from
 * everything above. The club layout has already established there is a session;
 * what these can meet is an account holding one and lacking
 * `platform.manage_strain_catalogue`. The page turns that into a 404, so an
 * account that may not manage the catalogue is told there is nothing at the
 * address rather than shown a screen full of refusals.
 */

/** Both the statuses that mean "you may not see this", so a caller handles one branch. */
const REFUSED_STATUSES = [401, 403]

const refusable = async <T>(read: () => Promise<T>): Promise<T | null> => {
  try {
    return await read()
  } catch (error) {
    if (error instanceof ApiError && REFUSED_STATUSES.includes(error.status)) {
      return null
    }
    throw error
  }
}

/** The catalogue as the list screen first draws it, or null when refused. */
export async function getStrains(): Promise<StrainRow[] | null> {
  return refusable(() => serverFetch<StrainRow[]>('/api/catalogue/strains'))
}

/** One strain in full, or null when refused or absent. */
export async function getStrain(id: string): Promise<Strain | null> {
  try {
    return await serverFetch<Strain>(`/api/catalogue/strains/${id}`)
  } catch (error) {
    if (
      error instanceof ApiError &&
      [...REFUSED_STATUSES, 404].includes(error.status)
    ) {
      // A 404 folds in here rather than throwing: the page's answer to all three
      // is the same page, and separating them would be a distinction with no
      // rendering behind it.
      return null
    }
    throw error
  }
}

/** Both vocabularies, or null when refused. */
export async function getVocabularies(): Promise<Vocabularies | null> {
  return refusable(() => serverFetch<Vocabularies>('/api/catalogue/terms'))
}

/**
 * The growers a strain may be reserved to, or an empty list.
 *
 * Empty rather than null on failure, and that is the one asymmetry here. The
 * picker's empty option — "Any cultivator may offer it" — is a valid and
 * commonly correct answer, so a form with no growers to choose from is still a
 * usable form. Taking the whole screen down because one dropdown could not be
 * filled would be a poor trade.
 */
export async function getCultivators(): Promise<Cultivator[]> {
  try {
    return await serverFetch<Cultivator[]>('/api/catalogue/cultivators')
  } catch {
    return []
  }
}

/* -------------------------------------------------------------------------- */
/* The membership register                                                     */
/* -------------------------------------------------------------------------- */

/*
 * Read on the server so the whole screen is in the first paint, for the reason
 * `getProfile` and `getStrains` give. It matters more here than on either:
 * a register is the screen an administrator scans and searches, and one that
 * arrives empty and fills in a moment later is a screen they will have started
 * typing a search into before the rows land underneath them.
 *
 * `null`-on-403 as well as on-401, matching the catalogue reads. The club layout
 * has already established there is a session; what these can meet is an account
 * holding one and lacking `platform.disable_user`. The page turns that into a
 * 404, so an account that may not manage the membership is told there is nothing
 * at the address rather than shown a screen full of refusals.
 */

/** The register as the list screen first draws it, or null when refused. */
export async function getMembers(): Promise<MemberRow[] | null> {
  return refusable(() => serverFetch<MemberRow[]>('/api/members'))
}

/**
 * One member in full, or null when refused or absent.
 *
 * The three statuses fold together for the reason `getStrain` gives: the page's
 * answer to all three is the same page, and separating them would be a
 * distinction with no rendering behind it. Here it is also the safer answer —
 * a 404 and a 403 that render differently would tell somebody without the
 * permission which account ids exist.
 */
export async function getMember(id: string): Promise<Member | null> {
  try {
    return await serverFetch<Member>(`/api/members/${id}`)
  } catch (error) {
    if (
      error instanceof ApiError &&
      [...REFUSED_STATUSES, 404].includes(error.status)
    ) {
      return null
    }
    throw error
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
