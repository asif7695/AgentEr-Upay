"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Skeleton } from "@/components/neu";
import { useAuth } from "@/lib/session";

export default function Index() {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    router.replace(!user ? "/login" : user.role === "admin" ? "/admin" : "/agent");
  }, [ready, user, router]);
  return <div className="mx-auto max-w-md p-8" aria-busy="true"><Skeleton className="h-40" /></div>;
}
