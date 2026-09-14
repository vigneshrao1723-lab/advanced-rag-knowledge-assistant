import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api-client";

const mockResetPassword = vi.fn();
const mockPush = vi.fn();
let mockSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => mockSearchParams,
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    resetPassword: (...args: [string, string]) => mockResetPassword(...args),
  };
});

import ResetPasswordPage from "@/app/reset-password/page";

async function fillAndSubmit(
  user: ReturnType<typeof userEvent.setup>,
  { newPassword, confirmPassword }: { newPassword: string; confirmPassword: string }
) {
  await user.type(screen.getByLabelText("New password"), newPassword);
  await user.type(screen.getByLabelText("Confirm new password"), confirmPassword);
  await user.click(screen.getByRole("button", { name: /reset password/i }));
}

describe("ResetPasswordPage", () => {
  afterEach(() => {
    mockResetPassword.mockReset();
    mockPush.mockReset();
    mockSearchParams = new URLSearchParams();
  });

  it("resets the password using the token from the URL, then offers to go to login", async () => {
    mockSearchParams = new URLSearchParams({ token: "raw-reset-token-from-email-link" });
    mockResetPassword.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await fillAndSubmit(user, {
      newPassword: "a brand new password",
      confirmPassword: "a brand new password",
    });

    await waitFor(() =>
      expect(mockResetPassword).toHaveBeenCalledWith(
        "raw-reset-token-from-email-link",
        "a brand new password"
      )
    );
    expect(await screen.findByText(/signed out everywhere/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /go to log in/i }));
    expect(mockPush).toHaveBeenCalledWith("/login");
  });

  it("shows a missing-token message and no form when the URL has no token", () => {
    mockSearchParams = new URLSearchParams();
    render(<ResetPasswordPage />);

    expect(screen.getByText(/missing its token/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
    expect(mockResetPassword).not.toHaveBeenCalled();
  });

  it("shows the backend's error message for an invalid/expired/used token", async () => {
    mockSearchParams = new URLSearchParams({ token: "stale-token" });
    mockResetPassword.mockRejectedValue(new ApiError(400, "This reset link has expired."));
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await fillAndSubmit(user, {
      newPassword: "a brand new password",
      confirmPassword: "a brand new password",
    });

    expect(await screen.findByText(/this reset link has expired/i)).toBeInTheDocument();
  });

  it("shows the backend's error message for an already-used token", async () => {
    mockSearchParams = new URLSearchParams({ token: "used-token" });
    mockResetPassword.mockRejectedValue(
      new ApiError(400, "This reset link has already been used.")
    );
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await fillAndSubmit(user, {
      newPassword: "a brand new password",
      confirmPassword: "a brand new password",
    });

    expect(await screen.findByText(/already been used/i)).toBeInTheDocument();
  });

  it("shows the backend's error message for an invalid token", async () => {
    mockSearchParams = new URLSearchParams({ token: "garbage-token" });
    mockResetPassword.mockRejectedValue(new ApiError(400, "This reset link is invalid."));
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await fillAndSubmit(user, {
      newPassword: "a brand new password",
      confirmPassword: "a brand new password",
    });

    expect(await screen.findByText(/this reset link is invalid/i)).toBeInTheDocument();
  });

  it("requires at least 8 characters before submitting", async () => {
    mockSearchParams = new URLSearchParams({ token: "some-token" });
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await fillAndSubmit(user, { newPassword: "short", confirmPassword: "short" });

    expect(await screen.findByText("Password must be at least 8 characters.")).toBeInTheDocument();
    expect(mockResetPassword).not.toHaveBeenCalled();
  });

  it("rejects submission when the confirmation does not match the new password", async () => {
    mockSearchParams = new URLSearchParams({ token: "some-token" });
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await fillAndSubmit(user, {
      newPassword: "a brand new password",
      confirmPassword: "a different password",
    });

    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(mockResetPassword).not.toHaveBeenCalled();
  });

  it("never writes to localStorage or sessionStorage", async () => {
    mockSearchParams = new URLSearchParams({ token: "raw-reset-token" });
    mockResetPassword.mockResolvedValue(undefined);
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    render(<ResetPasswordPage />);

    await fillAndSubmit(user, {
      newPassword: "a brand new password",
      confirmPassword: "a brand new password",
    });
    await waitFor(() => expect(mockResetPassword).toHaveBeenCalled());

    expect(setItemSpy).not.toHaveBeenCalled();
    setItemSpy.mockRestore();
  });
});
