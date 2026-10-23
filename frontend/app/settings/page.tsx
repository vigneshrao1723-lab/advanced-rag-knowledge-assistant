"use client";

import { useCallback, useEffect, useState } from "react";
import { Laptop, Mail, ShieldCheck } from "lucide-react";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { SessionInfo } from "@/lib/schemas";
import { describeDevice } from "@/lib/user-agent";

function SettingsContent() {
  const { user } = useAuth();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    setIsLoading(true);
    try {
      setSessions(await api.listSessions());
      setError(null);
    } catch {
      setError("Could not load sessions.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Standard fetch-on-mount pattern — no data-fetching library is
    // warranted for this issue's minimal session-management screen.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSessions();
  }, [loadSessions]);

  async function handleRevoke(sessionId: string) {
    setRevokingId(sessionId);
    try {
      await api.revokeSession(sessionId);
      await loadSessions();
    } catch {
      setError("Could not revoke that session.");
    } finally {
      setRevokingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-indigo-600" aria-hidden="true" />
            Profile
          </CardTitle>
          <CardDescription>Account settings.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm">
          <p className="flex items-center gap-2">
            <Mail className="text-muted-foreground size-4" aria-hidden="true" />
            {user?.email}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Laptop className="size-4 text-indigo-600" aria-hidden="true" />
            Active sessions
          </CardTitle>
          <CardDescription>Devices/sessions currently signed in to your account.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-muted-foreground text-sm">Loading…</p>
          ) : error ? (
            <p className="text-destructive text-sm">{error}</p>
          ) : sessions.length === 0 ? (
            <p className="text-muted-foreground text-sm">No active sessions.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {sessions.map((session) => (
                <li
                  key={session.id}
                  className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 p-3"
                >
                  <div className="flex items-start gap-3 text-sm">
                    <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
                      <Laptop className="size-4" aria-hidden="true" />
                    </div>
                    <div>
                      <p className="font-medium">
                        {describeDevice(session.device_label)}
                        {session.is_current && (
                          <span className="ml-2 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                            this device
                          </span>
                        )}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        Last used {new Date(session.last_used_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={revokingId === session.id}
                    onClick={() => handleRevoke(session.id)}
                  >
                    {revokingId === session.id ? "Revoking…" : "Revoke"}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <ProtectedRoute>
      <SettingsContent />
    </ProtectedRoute>
  );
}
