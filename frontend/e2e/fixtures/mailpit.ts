/**
 * Reads password-reset email through Mailpit's real REST API (the same
 * SMTP capture `infra/compose/docker-compose.yml` already documents:
 * "Playwright reads the reset email via the API"). This talks to a real
 * running Mailpit instance over HTTP — not a mock of the email
 * provider; the backend's own `EMAIL_PROVIDER=smtp` path sends here
 * exactly as it would to a real mail relay.
 */

const MAILPIT_URL = process.env.PLAYWRIGHT_MAILPIT_URL ?? "http://localhost:8025";

interface MailpitMessageSummary {
  ID: string;
  To: { Address: string }[];
  Subject: string;
  Created: string;
}

interface MailpitSearchResponse {
  messages: MailpitMessageSummary[];
}

interface MailpitMessageDetail {
  Text: string;
}

/**
 * Polls Mailpit for the most recent message sent to `email` whose
 * subject contains `subjectContains`, up to `timeoutMs`. A short poll
 * loop, not a fixed sleep — real SMTP delivery through a real capture
 * server has a small, variable, genuine delay, and this waits on the
 * actual condition (a matching message exists) rather than guessing a
 * duration.
 */
export async function findLatestMailpitMessage(
  email: string,
  subjectContains: string,
  timeoutMs = 10_000
): Promise<MailpitMessageSummary> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown = null;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(
        `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`
      );
      if (response.ok) {
        const body = (await response.json()) as MailpitSearchResponse;
        const matches = body.messages
          .filter((message) => message.Subject.includes(subjectContains))
          .sort((a, b) => new Date(b.Created).getTime() - new Date(a.Created).getTime());
        if (matches.length > 0) return matches[0];
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }

  throw new Error(
    `No Mailpit message to ${email} with subject containing ${JSON.stringify(subjectContains)} ` +
      `within ${timeoutMs}ms${lastError ? ` (last error: ${String(lastError)})` : ""}`
  );
}

export async function fetchMailpitMessageText(id: string): Promise<string> {
  const response = await fetch(`${MAILPIT_URL}/api/v1/message/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch Mailpit message ${id}: HTTP ${response.status}`);
  }
  const body = (await response.json()) as MailpitMessageDetail;
  return body.Text;
}

const RESET_LINK_RE = /(http:\/\/\S+\/reset-password\?token=\S+)/;

export function extractResetLink(emailText: string): string {
  const match = emailText.match(RESET_LINK_RE);
  if (!match) {
    throw new Error("No reset link found in the captured email body.");
  }
  return match[1];
}
