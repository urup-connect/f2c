"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { logout } from "@/lib/api";

export function SignOutButton() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  async function handleClick() {
    await logout();
    // Refresh so every server component re-reads the now-absent session.
    startTransition(() => {
      router.refresh();
      router.push("/");
    });
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={isPending}
      className="rounded-md border border-neutral-300 px-3 py-1.5 font-medium hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
    >
      {isPending ? "Signing out…" : "Sign out"}
    </button>
  );
}
