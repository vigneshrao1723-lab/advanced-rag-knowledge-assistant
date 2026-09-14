"use client";

import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import { ForgotPasswordFormSchema } from "@/lib/schemas";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // The backend always returns the same generic message regardless of
  // whether the email exists — showing that message is itself the
  // enumeration-resistant behavior; there is no "found"/"not found" state.
  const [submittedMessage, setSubmittedMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFieldError(null);
    setSubmitError(null);

    const parsed = ForgotPasswordFormSchema.safeParse({ email });
    if (!parsed.success) {
      setFieldError(parsed.error.issues[0]?.message ?? "Invalid input.");
      return;
    }

    setIsSubmitting(true);
    try {
      const { message } = await api.forgotPassword(parsed.data.email);
      setSubmittedMessage(message);
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : "Something went wrong.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <Card>
        <CardHeader>
          <CardTitle>Forgot password</CardTitle>
          <CardDescription>We&apos;ll email you a link to reset it.</CardDescription>
        </CardHeader>
        <CardContent>
          {submittedMessage ? (
            <p className="text-sm">{submittedMessage}</p>
          ) : (
            <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="email" className="text-sm font-medium">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="border-input bg-background rounded-md border px-3 py-2 text-sm"
                />
              </div>
              {fieldError && <p className="text-destructive text-sm">{fieldError}</p>}
              {submitError && <p className="text-destructive text-sm">{submitError}</p>}
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Sending…" : "Send reset link"}
              </Button>
            </form>
          )}
          <p className="text-muted-foreground mt-4 text-sm">
            <Link href="/login" className="text-foreground underline">
              Back to log in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
