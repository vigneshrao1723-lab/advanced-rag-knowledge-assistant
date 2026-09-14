"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { LoginFormSchema } from "@/lib/schemas";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFieldError(null);
    setSubmitError(null);

    const parsed = LoginFormSchema.safeParse({ email, password });
    if (!parsed.success) {
      setFieldError(parsed.error.issues[0]?.message ?? "Invalid input.");
      return;
    }

    setIsSubmitting(true);
    try {
      await login(parsed.data.email, parsed.data.password);
      router.push("/dashboard");
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : "Log in failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <Card>
        <CardHeader>
          <CardTitle>Log in</CardTitle>
          <CardDescription>Access your workspaces.</CardDescription>
        </CardHeader>
        <CardContent>
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
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <label htmlFor="password" className="text-sm font-medium">
                  Password
                </label>
                <Link
                  href="/forgot-password"
                  className="text-muted-foreground hover:text-foreground text-xs underline"
                >
                  Forgot password?
                </Link>
              </div>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="border-input bg-background rounded-md border px-3 py-2 text-sm"
              />
            </div>
            {fieldError && <p className="text-destructive text-sm">{fieldError}</p>}
            {submitError && <p className="text-destructive text-sm">{submitError}</p>}
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Logging in…" : "Log in"}
            </Button>
          </form>
          <p className="text-muted-foreground mt-4 text-sm">
            Don&apos;t have an account?{" "}
            <Link href="/register" className="text-foreground underline">
              Register
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
