"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getApiBaseUrl } from "@/lib/config";

type Status = "checking" | "ready" | "not_ready" | "unreachable";

/**
 * Calls the real backend readiness endpoint — this is infrastructure
 * verification for Issue #1 (proving the frontend can reach the backend
 * and the backend can reach the database), not a product feature.
 */
export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const response = await fetch(`${getApiBaseUrl()}/api/v1/health/ready`);
        const body: { status?: string } = await response.json();
        if (!cancelled) {
          setStatus(body.status === "ready" ? "ready" : "not_ready");
        }
      } catch {
        if (!cancelled) {
          setStatus("unreachable");
        }
      }
    }

    void check();
    return () => {
      cancelled = true;
    };
  }, []);

  const label: Record<Status, string> = {
    checking: "Checking…",
    ready: "Backend reachable, database ready",
    not_ready: "Backend reachable, database not ready",
    unreachable: "Backend unreachable",
  };

  const dotColor: Record<Status, string> = {
    checking: "bg-muted-foreground",
    ready: "bg-green-500",
    not_ready: "bg-yellow-500",
    unreachable: "bg-destructive",
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Backend status</CardTitle>
        <CardDescription>Live readiness check against {getApiBaseUrl()}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-2 text-sm">
          <span className={`size-2 rounded-full ${dotColor[status]}`} />
          <span>{label[status]}</span>
        </div>
      </CardContent>
    </Card>
  );
}
