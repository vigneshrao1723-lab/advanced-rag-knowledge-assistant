import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api-client";

const mockForgotPassword = vi.fn();

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return { ...actual, forgotPassword: (...args: [string]) => mockForgotPassword(...args) };
});

import ForgotPasswordPage from "@/app/forgot-password/page";

describe("ForgotPasswordPage", () => {
  afterEach(() => {
    mockForgotPassword.mockReset();
  });

  it("shows the backend's generic message after a successful submit", async () => {
    mockForgotPassword.mockResolvedValue({
      message: "If an account with that email exists, password reset instructions have been sent.",
    });
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(mockForgotPassword).toHaveBeenCalledWith("user@example.com");
    expect(
      await screen.findByText(/password reset instructions have been sent/i)
    ).toBeInTheDocument();
    // The form itself is replaced by the message — no email field left to
    // resubmit, matching the "one generic response, no further signal"
    // enumeration-resistant design.
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  });

  it("shows the exact same generic message regardless of whether the email exists", async () => {
    const genericMessage =
      "If an account with that email exists, password reset instructions have been sent.";
    mockForgotPassword.mockResolvedValue({ message: genericMessage });
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText("Email"), "unknown@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByText(genericMessage)).toBeInTheDocument();
  });

  it("requires a valid email before submitting", async () => {
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(mockForgotPassword).not.toHaveBeenCalled();
  });

  it("shows an error (e.g. rate limited) without replacing the form with a success message", async () => {
    mockForgotPassword.mockRejectedValue(new ApiError(429, "Too many requests."));
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByText(/too many requests/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("never writes to localStorage or sessionStorage", async () => {
    mockForgotPassword.mockResolvedValue({ message: "generic message" });
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));
    await waitFor(() => expect(mockForgotPassword).toHaveBeenCalled());

    expect(setItemSpy).not.toHaveBeenCalled();
    setItemSpy.mockRestore();
  });
});
