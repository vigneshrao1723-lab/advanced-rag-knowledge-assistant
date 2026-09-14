import { z } from "zod";

// Mirrors backend/app/schemas/*.py — validated at the API boundary per
// AGENTS.md's "Zod for runtime validation at API boundaries".

export const WorkspaceRoleSchema = z.enum(["OWNER", "ADMIN", "MEMBER", "VIEWER"]);
export type WorkspaceRole = z.infer<typeof WorkspaceRoleSchema>;

export const UserSchema = z.object({
  id: z.string(),
  email: z.string(),
  created_at: z.string(),
});
export type User = z.infer<typeof UserSchema>;

// Access/refresh tokens are delivered as HttpOnly cookies, never in the
// JSON body (ADR 0005) — the client only ever receives the user object.
export const AuthResponseSchema = z.object({
  user: UserSchema,
});
export type AuthResponse = z.infer<typeof AuthResponseSchema>;

export const SessionInfoSchema = z.object({
  id: z.string(),
  device_label: z.string().nullable(),
  created_at: z.string(),
  last_used_at: z.string(),
  expires_at: z.string(),
  is_current: z.boolean(),
});
export type SessionInfo = z.infer<typeof SessionInfoSchema>;
export const SessionListSchema = z.array(SessionInfoSchema);

export const WorkspaceSchema = z.object({
  id: z.string(),
  name: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  my_role: WorkspaceRoleSchema,
});
export type Workspace = z.infer<typeof WorkspaceSchema>;
export const WorkspaceListSchema = z.array(WorkspaceSchema);

export const MemberSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  role: WorkspaceRoleSchema,
  created_at: z.string(),
});
export type Member = z.infer<typeof MemberSchema>;
export const MemberListSchema = z.array(MemberSchema);

export const ErrorBodySchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    request_id: z.string().nullable().optional(),
  }),
});

export const RegisterFormSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
});
export type RegisterForm = z.infer<typeof RegisterFormSchema>;

export const LoginFormSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});
export type LoginForm = z.infer<typeof LoginFormSchema>;

export const ForgotPasswordFormSchema = z.object({
  email: z.string().email("Enter a valid email address."),
});
export type ForgotPasswordForm = z.infer<typeof ForgotPasswordFormSchema>;

export const MessageResponseSchema = z.object({
  message: z.string(),
});
export type MessageResponse = z.infer<typeof MessageResponseSchema>;

// Mirrors the backend's reset-password validation (Field(min_length=8,
// max_length=256) in `backend/app/schemas/auth.py`) so the form fails
// fast client-side with the same bound the server enforces. The
// confirmation field exists only to catch typos before submitting — the
// backend has no notion of a "confirm password" value, so it never leaves
// this schema.
export const ResetPasswordFormSchema = z
  .object({
    newPassword: z.string().min(8, "Password must be at least 8 characters."),
    confirmPassword: z.string().min(1, "Please confirm your new password."),
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  });
export type ResetPasswordForm = z.infer<typeof ResetPasswordFormSchema>;
