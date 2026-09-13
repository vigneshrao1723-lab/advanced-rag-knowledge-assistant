"use client";

import { useCallback, useEffect, useState } from "react";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { SessionInfo } from "@/lib/schemas";

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
          <CardTitle>Profile</CardTitle>
          <CardDescription>Account settings.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm">
          <p>
            <span className="text-muted-foreground">Email:</span> {user?.email}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Active sessions</CardTitle>
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
                  className="flex items-center justify-between gap-4 border-b pb-3 last:border-b-0 last:pb-0"
                >
                  <div className="text-sm">
                    <p className="font-medium">
                      {session.device_label ?? "Unknown device"}
                      {session.is_current && (
                        <span className="text-muted-foreground ml-2 text-xs">(this device)</span>
                      )}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      Last used {new Date(session.last_used_at).toLocaleString()}
                    </p>
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
