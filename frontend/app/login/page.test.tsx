import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api-client";

const mockPush = vi.fn();
const mockLogin = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ login: mockLogin }),
}));

import LoginPage from "@/app/login/page";

describe("LoginPage", () => {
  afterEach(() => {
    mockPush.mockReset();
    mockLogin.mockReset();
  });

  it("logs in and redirects to /dashboard on success", async () => {
    mockLogin.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-password");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() =>
      expect(mockLogin).toHaveBeenCalledWith("user@example.com", "correct-password")
    );
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows an invalid-credentials error without redirecting", async () => {
    mockLogin.mockRejectedValue(new ApiError(401, "Incorrect email or password."));
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    expect(await screen.findByText(/incorrect email or password/i)).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("requires an email before submitting", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Password"), "something");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(mockLogin).not.toHaveBeenCalled();
  });
});
