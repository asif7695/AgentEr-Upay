"use client";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { Skeleton } from "@/components/neu";
import { useAuth } from "@/lib/session";
import type { Role } from "@/lib/types";

/** Client-side route guard. The API enforces roles independently; this only routes people to the right place. */
export function Guard({ role, children }: { role: Role; children: ReactNode }) {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    if (!user) router.replace("/login");
    else if (user.role !== role) router.replace(user.role === "admin" ? "/admin" : "/agent");
  }, [ready, user, role, router]);
  if (!ready || !user || user.role !== role) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4 p-6" aria-busy="true">
        <Skeleton className="h-16" /><Skeleton className="h-64" /><Skeleton className="h-40" />
      </div>
    );
  }
  return <>{children}</>;
}
