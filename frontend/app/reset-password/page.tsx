"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import { ResetPasswordFormSchema } from "@/lib/schemas";

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const router = useRouter();
  // The token lives only in the URL (from the emailed link) and is sent
  // straight through to the backend on submit — it is never persisted to
  // localStorage/sessionStorage, and it authenticates nothing on its own
  // (it isn't a session token, just a one-time proof of email ownership).
  const token = searchParams.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [succeeded, setSucceeded] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFieldError(null);
    setSubmitError(null);

    const parsed = ResetPasswordFormSchema.safeParse({ newPassword, confirmPassword });
    if (!parsed.success) {
      setFieldError(parsed.error.issues[0]?.message ?? "Invalid input.");
      return;
    }
    if (!token) {
      setSubmitError("This reset link is missing its token.");
      return;
    }

    setIsSubmitting(true);
    try {
      await api.resetPassword(token, parsed.data.newPassword);
      setSucceeded(true);
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : "Something went wrong.");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (succeeded) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm">
          Your password has been reset. You&apos;ve been signed out everywhere, so log in again
          with your new password.
        </p>
        <Button onClick={() => router.push("/login")}>Go to log in</Button>
      </div>
    );
  }

  if (!token) {
    return (
      <p className="text-destructive text-sm">
        This reset link is missing its token. Request a new one from the{" "}
        <Link href="/forgot-password" className="underline">
          forgot password
        </Link>{" "}
        page.
      </p>
    );
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="new-password" className="text-sm font-medium">
          New password
        </label>
        <input
          id="new-password"
          type="password"
          autoComplete="new-password"
          required
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className="border-input bg-background rounded-md border px-3 py-2 text-sm"
        />
        <p className="text-muted-foreground text-xs">At least 8 characters.</p>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="confirm-password" className="text-sm font-medium">
          Confirm new password
        </label>
        <input
          id="confirm-password"
          type="password"
          autoComplete="new-password"
          required
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          className="border-input bg-background rounded-md border px-3 py-2 text-sm"
        />
      </div>
      {fieldError && <p className="text-destructive text-sm">{fieldError}</p>}
      {submitError && <p className="text-destructive text-sm">{submitError}</p>}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Resetting…" : "Reset password"}
      </Button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="mx-auto max-w-sm">
      <Card>
        <CardHeader>
          <CardTitle>Reset password</CardTitle>
          <CardDescription>Choose a new password for your account.</CardDescription>
        </CardHeader>
        <CardContent>
          <Suspense fallback={<p className="text-muted-foreground text-sm">Loading…</p>}>
            <ResetPasswordForm />
          </Suspense>
        </CardContent>
      </Card>
    </div>
  );
}
