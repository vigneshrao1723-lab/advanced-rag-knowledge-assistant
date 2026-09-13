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

export const TokenResponseSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.string(),
  expires_in: z.number(),
  user: UserSchema,
});
export type TokenResponse = z.infer<typeof TokenResponseSchema>;

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
