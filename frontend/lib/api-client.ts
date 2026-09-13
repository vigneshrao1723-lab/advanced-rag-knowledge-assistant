import { getApiBaseUrl } from "@/lib/config";
import { clearAuth, loadAuth, saveAuth } from "@/lib/auth-storage";
import {
  ErrorBodySchema,
  MemberListSchema,
  MemberSchema,
  SessionListSchema,
  TokenResponseSchema,
  UserSchema,
  WorkspaceListSchema,
  WorkspaceSchema,
  type Member,
  type SessionInfo,
  type TokenResponse,
  type User,
  type Workspace,
  type WorkspaceRole,
} from "@/lib/schemas";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const body = ErrorBodySchema.parse(await response.json());
    return body.error.message;
  } catch {
    return `Request failed (${response.status}).`;
  }
}

async function rawFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
}

let refreshInFlight: Promise<boolean> | null = null;

/** Refreshes the stored tokens exactly once even if multiple requests hit
 * a 401 concurrently. Returns whether the refresh succeeded. */
async function refreshTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const stored = loadAuth();
    if (!stored) return false;

    const response = await rawFetch("/api/v1/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: stored.refreshToken }),
    });
    if (!response.ok) {
      clearAuth();
      return false;
    }

    const tokens = TokenResponseSchema.parse(await response.json());
    saveAuth({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      user: tokens.user,
    });
    return true;
  })();

  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

/** Authenticated fetch: attaches the access token and retries once, after
 * a token refresh, on a 401. Throws ApiError for any non-2xx response. */
async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const stored = loadAuth();
  const withAuth = (token: string | undefined): RequestInit => ({
    ...init,
    headers: {
      ...init?.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  let response = await rawFetch(path, withAuth(stored?.accessToken));

  if (response.status === 401 && stored) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      const retried = loadAuth();
      response = await rawFetch(path, withAuth(retried?.accessToken));
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return response;
}

// --- Auth ---

export async function register(email: string, password: string): Promise<TokenResponse> {
  const response = await rawFetch("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) throw new ApiError(response.status, await parseErrorMessage(response));
  return TokenResponseSchema.parse(await response.json());
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const response = await rawFetch("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) throw new ApiError(response.status, await parseErrorMessage(response));
  return TokenResponseSchema.parse(await response.json());
}

export async function logout(refreshToken: string): Promise<void> {
  await rawFetch("/api/v1/auth/logout", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export async function getCurrentUser(): Promise<User> {
  const response = await authFetch("/api/v1/users/me");
  return UserSchema.parse(await response.json());
}

export async function listSessions(): Promise<SessionInfo[]> {
  const response = await authFetch("/api/v1/auth/sessions");
  return SessionListSchema.parse(await response.json());
}

export async function revokeSession(sessionId: string): Promise<void> {
  await authFetch(`/api/v1/auth/sessions/${sessionId}`, { method: "DELETE" });
}

// --- Workspaces ---

export async function listWorkspaces(): Promise<Workspace[]> {
  const response = await authFetch("/api/v1/workspaces");
  return WorkspaceListSchema.parse(await response.json());
}

export async function createWorkspace(name: string): Promise<Workspace> {
  const response = await authFetch("/api/v1/workspaces", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  return WorkspaceSchema.parse(await response.json());
}

export async function updateWorkspace(workspaceId: string, name: string): Promise<Workspace> {
  const response = await authFetch(`/api/v1/workspaces/${workspaceId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
  return WorkspaceSchema.parse(await response.json());
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  await authFetch(`/api/v1/workspaces/${workspaceId}`, { method: "DELETE" });
}

export async function listMembers(workspaceId: string): Promise<Member[]> {
  const response = await authFetch(`/api/v1/workspaces/${workspaceId}/members`);
  return MemberListSchema.parse(await response.json());
}

export async function addMember(
  workspaceId: string,
  email: string,
  role: WorkspaceRole
): Promise<Member> {
  const response = await authFetch(`/api/v1/workspaces/${workspaceId}/members`, {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
  return MemberSchema.parse(await response.json());
}

export async function updateMemberRole(
  workspaceId: string,
  userId: string,
  role: WorkspaceRole
): Promise<Member> {
  const response = await authFetch(`/api/v1/workspaces/${workspaceId}/members/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });
  return MemberSchema.parse(await response.json());
}

export async function removeMember(workspaceId: string, userId: string): Promise<void> {
  await authFetch(`/api/v1/workspaces/${workspaceId}/members/${userId}`, { method: "DELETE" });
}
