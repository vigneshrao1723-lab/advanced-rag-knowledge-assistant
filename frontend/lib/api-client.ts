import { getApiBaseUrl } from "@/lib/config";
import { getCsrfToken } from "@/lib/csrf";
import {
  AuthResponseSchema,
  ConversationListSchema,
  ConversationSchema,
  DocumentListSchema,
  DocumentSchema,
  ErrorBodySchema,
  MemberListSchema,
  MemberSchema,
  MessageListSchema,
  MessageResponseSchema,
  MessageSchema,
  SessionListSchema,
  UserSchema,
  VoiceMessageSchema,
  WorkspaceListSchema,
  WorkspaceSchema,
  type AuthResponse,
  type Conversation,
  type Document,
  type Member,
  type Message,
  type MessageResponse,
  type SessionInfo,
  type User,
  type VoiceMessage,
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

const STATE_CHANGING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// A 401 from any of these means exactly what it says (no session, bad
// credentials, or a dead refresh token) — never "the access token just
// needs refreshing". They must never trigger the auto-refresh-and-retry
// behavior in `apiRequest` below, or a login/refresh failure could recurse.
const NO_RETRY_PATHS = new Set([
  "/api/v1/auth/login",
  "/api/v1/auth/register",
  "/api/v1/auth/refresh",
  "/api/v1/auth/logout",
  "/api/v1/auth/csrf",
  "/api/v1/auth/forgot-password",
  "/api/v1/auth/reset-password",
]);

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const body = ErrorBodySchema.parse(await response.json());
    return body.error.message;
  } catch {
    return `Request failed (${response.status}).`;
  }
}

/**
 * Every request goes through here. `credentials: "include"` sends/receives
 * the HttpOnly access/refresh cookies even though the frontend and backend
 * are different origins (ADR 0005) — this project never assumes they share
 * a site. State-changing methods get the CSRF header attached, sourced
 * from the non-HttpOnly `csrf_token` cookie (`lib/csrf.ts`). Authentication
 * tokens are never read, stored, or forwarded by this code — the browser
 * handles the cookies entirely on its own.
 */
function buildRequestInit(method: string, init?: RequestInit): RequestInit {
  // `FormData` bodies (file upload) must NOT get an explicit
  // "Content-Type" -- the browser sets it itself, including the
  // multipart boundary, only when it builds the request from a FormData
  // body directly.
  const isFormData = init?.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (STATE_CHANGING_METHODS.has(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  }
  return { ...init, method, credentials: "include", headers };
}

async function rawRequest(path: string, method: string, init?: RequestInit): Promise<Response> {
  return fetch(`${getApiBaseUrl()}${path}`, buildRequestInit(method, init));
}

let refreshInFlight: Promise<boolean> | null = null;

/** Refreshes the session cookies exactly once even if multiple requests
 * hit a 401 concurrently. Returns whether the refresh succeeded. */
async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const response = await rawRequest("/api/v1/auth/refresh", "POST");
    return response.ok;
  })();

  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

interface RequestOptions extends RequestInit {
  /** Set to false to skip the automatic refresh-and-retry on a 401 — used
   * for the initial "am I logged in at all" check on app mount, so an
   * anonymous visitor doesn't burn a refresh attempt (and its rate limit)
   * on every page load. */
  retryOn401?: boolean;
}

async function apiRequest(
  path: string,
  method: string,
  { retryOn401 = true, ...init }: RequestOptions = {}
): Promise<Response> {
  let response = await rawRequest(path, method, init);

  if (response.status === 401 && retryOn401 && !NO_RETRY_PATHS.has(path)) {
    const refreshed = await refreshSession();
    if (refreshed) {
      response = await rawRequest(path, method, init);
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return response;
}

// --- Auth ---

export async function register(email: string, password: string): Promise<AuthResponse> {
  const response = await apiRequest("/api/v1/auth/register", "POST", {
    body: JSON.stringify({ email, password }),
  });
  return AuthResponseSchema.parse(await response.json());
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const response = await apiRequest("/api/v1/auth/login", "POST", {
    body: JSON.stringify({ email, password }),
  });
  return AuthResponseSchema.parse(await response.json());
}

export async function logout(): Promise<void> {
  await apiRequest("/api/v1/auth/logout", "POST");
}

export async function forgotPassword(email: string): Promise<MessageResponse> {
  const response = await apiRequest("/api/v1/auth/forgot-password", "POST", {
    body: JSON.stringify({ email }),
  });
  return MessageResponseSchema.parse(await response.json());
}

export async function resetPassword(token: string, newPassword: string): Promise<void> {
  await apiRequest("/api/v1/auth/reset-password", "POST", {
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export async function getCurrentUser(): Promise<User> {
  const response = await apiRequest("/api/v1/users/me", "GET", { retryOn401: false });
  return UserSchema.parse(await response.json());
}

export async function listSessions(): Promise<SessionInfo[]> {
  const response = await apiRequest("/api/v1/auth/sessions", "GET");
  return SessionListSchema.parse(await response.json());
}

export async function revokeSession(sessionId: string): Promise<void> {
  await apiRequest(`/api/v1/auth/sessions/${sessionId}`, "DELETE");
}

// --- Workspaces ---

export async function listWorkspaces(): Promise<Workspace[]> {
  const response = await apiRequest("/api/v1/workspaces", "GET");
  return WorkspaceListSchema.parse(await response.json());
}

export async function createWorkspace(name: string): Promise<Workspace> {
  const response = await apiRequest("/api/v1/workspaces", "POST", {
    body: JSON.stringify({ name }),
  });
  return WorkspaceSchema.parse(await response.json());
}

export async function updateWorkspace(workspaceId: string, name: string): Promise<Workspace> {
  const response = await apiRequest(`/api/v1/workspaces/${workspaceId}`, "PATCH", {
    body: JSON.stringify({ name }),
  });
  return WorkspaceSchema.parse(await response.json());
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  await apiRequest(`/api/v1/workspaces/${workspaceId}`, "DELETE");
}

export async function listMembers(workspaceId: string): Promise<Member[]> {
  const response = await apiRequest(`/api/v1/workspaces/${workspaceId}/members`, "GET");
  return MemberListSchema.parse(await response.json());
}

export async function addMember(
  workspaceId: string,
  email: string,
  role: WorkspaceRole
): Promise<Member> {
  const response = await apiRequest(`/api/v1/workspaces/${workspaceId}/members`, "POST", {
    body: JSON.stringify({ email, role }),
  });
  return MemberSchema.parse(await response.json());
}

export async function updateMemberRole(
  workspaceId: string,
  userId: string,
  role: WorkspaceRole
): Promise<Member> {
  const response = await apiRequest(
    `/api/v1/workspaces/${workspaceId}/members/${userId}`,
    "PATCH",
    { body: JSON.stringify({ role }) }
  );
  return MemberSchema.parse(await response.json());
}

export async function removeMember(workspaceId: string, userId: string): Promise<void> {
  await apiRequest(`/api/v1/workspaces/${workspaceId}/members/${userId}`, "DELETE");
}

// --- Documents ---

export async function listDocuments(workspaceId: string): Promise<Document[]> {
  const response = await apiRequest(`/api/v1/workspaces/${workspaceId}/documents`, "GET");
  return DocumentListSchema.parse(await response.json());
}

export async function getDocument(workspaceId: string, documentId: string): Promise<Document> {
  const response = await apiRequest(
    `/api/v1/workspaces/${workspaceId}/documents/${documentId}`,
    "GET"
  );
  return DocumentSchema.parse(await response.json());
}

export async function uploadDocument(workspaceId: string, file: File): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiRequest(`/api/v1/workspaces/${workspaceId}/documents`, "POST", {
    body: formData,
  });
  return DocumentSchema.parse(await response.json());
}

export async function processDocument(workspaceId: string, documentId: string): Promise<Document> {
  const response = await apiRequest(
    `/api/v1/workspaces/${workspaceId}/documents/${documentId}/process`,
    "POST"
  );
  return DocumentSchema.parse(await response.json());
}

// --- Conversations ---

export async function listConversations(workspaceId: string): Promise<Conversation[]> {
  const response = await apiRequest(`/api/v1/workspaces/${workspaceId}/conversations`, "GET");
  return ConversationListSchema.parse(await response.json());
}

export async function createConversation(workspaceId: string): Promise<Conversation> {
  const response = await apiRequest(`/api/v1/workspaces/${workspaceId}/conversations`, "POST");
  return ConversationSchema.parse(await response.json());
}

export async function listMessages(workspaceId: string, conversationId: string): Promise<Message[]> {
  const response = await apiRequest(
    `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
    "GET"
  );
  return MessageListSchema.parse(await response.json());
}

export async function postMessage(
  workspaceId: string,
  conversationId: string,
  content: string
): Promise<Message> {
  const response = await apiRequest(
    `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
    "POST",
    { body: JSON.stringify({ content }) }
  );
  return MessageSchema.parse(await response.json());
}

// --- Voice ---

export async function postVoiceMessage(
  workspaceId: string,
  conversationId: string,
  audio: Blob
): Promise<VoiceMessage> {
  const formData = new FormData();
  formData.append("audio", audio, "question.wav");
  const response = await apiRequest(
    `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/voice-messages`,
    "POST",
    { body: formData }
  );
  return VoiceMessageSchema.parse(await response.json());
}

/** A plain URL, not a fetch wrapper -- meant to be used directly as an
 * `<audio src>`. The browser attaches this app's auth cookies to a
 * same-site resource load like any other (no CSRF token needed; this
 * is a `GET`, and CSRF protection here only covers state-changing
 * methods -- see `buildRequestInit()`). */
export function getMessageAudioUrl(
  workspaceId: string,
  conversationId: string,
  messageId: string
): string {
  return `${getApiBaseUrl()}/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/messages/${messageId}/audio`;
}
