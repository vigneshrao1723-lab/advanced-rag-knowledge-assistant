import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api-client";

const mockPush = vi.fn();
const mockRegister = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ register: mockRegister }),
}));

import RegisterPage from "@/app/register/page";

describe("RegisterPage", () => {
  afterEach(() => {
    mockPush.mockReset();
    mockRegister.mockReset();
  });

  it("shows a validation error for a short password without calling the API", async () => {
    const user = userEvent.setup();
    render(<RegisterPage />);

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/password must be at least 8 characters/i)).toBeInTheDocument();
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it("shows a validation error for an invalid email", async () => {
    const user = userEvent.setup();
    render(<RegisterPage />);

    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.type(screen.getByLabelText("Password"), "a-fine-password");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it("registers and redirects to /dashboard on success", async () => {
    mockRegister.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<RegisterPage />);

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "a-fine-password");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(mockRegister).toHaveBeenCalledWith("user@example.com", "a-fine-password"));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows the server's error message when registration fails", async () => {
    mockRegister.mockRejectedValue(new ApiError(409, "An account with this email already exists."));
    const user = userEvent.setup();
    render(<RegisterPage />);

    await user.type(screen.getByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "a-fine-password");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
