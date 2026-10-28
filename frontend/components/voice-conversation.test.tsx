import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { VoiceConversationButton, VoiceConversationPanel } from "@/components/voice-conversation";
import type { ConversationPhase, UseVoiceConversation } from "@/lib/use-voice-conversation";

function fake(overrides: Partial<UseVoiceConversation> = {}): UseVoiceConversation {
  const phase: ConversationPhase = overrides.phase ?? "off";
  return {
    phase,
    active: phase !== "off" && phase !== "error",
    level: 0,
    heard: "",
    answer: "",
    error: null,
    notice: null,
    turns: 0,
    speakerName: null,
    start: vi.fn(),
    end: vi.fn(),
    stopSpeaking: vi.fn(),
    finishSpeaking: vi.fn(),
    retry: vi.fn(),
    ...overrides,
  };
}

const panelProps = {
  speakAnswers: true,
  onSpeakAnswersChange: vi.fn(),
  speechRate: 1,
  onSpeechRateChange: vi.fn(),
};

describe("VoiceConversationButton", () => {
  it("starts the conversation, and is unavailable while one is running", async () => {
    const voice = fake();
    const user = userEvent.setup();
    const { rerender } = render(<VoiceConversationButton voice={voice} />);
    await user.click(screen.getByRole("button", { name: /start voice conversation/i }));
    expect(voice.start).toHaveBeenCalled();

    rerender(<VoiceConversationButton voice={fake({ phase: "listening" })} />);
    expect(screen.getByRole("button", { name: /start voice conversation/i })).toBeDisabled();
  });
});

describe("VoiceConversationPanel", () => {
  it("renders nothing while off with nothing to say", () => {
    const { container } = render(<VoiceConversationPanel voice={fake()} {...panelProps} />);
    expect(container).toBeEmptyDOMElement();
  });

  it.each([
    ["listening", /listening… speak now/i],
    ["transcribing", /transcribing/i],
    ["thinking", /thinking/i],
    ["speaking", /speaking…/i],
  ] as const)("shows the %s state", (phase, label) => {
    render(<VoiceConversationPanel voice={fake({ phase })} {...panelProps} />);
    expect(screen.getByRole("status")).toHaveTextContent(label);
    expect(screen.getByRole("button", { name: /end conversation/i })).toBeInTheDocument();
  });

  it("offers 'I'm done talking' only while listening and 'Stop speaking' only while speaking", async () => {
    const listening = fake({ phase: "listening" });
    const user = userEvent.setup();
    const { rerender } = render(<VoiceConversationPanel voice={listening} {...panelProps} />);
    await user.click(screen.getByRole("button", { name: /i.m done talking/i }));
    expect(listening.finishSpeaking).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /stop speaking/i })).not.toBeInTheDocument();

    const speaking = fake({ phase: "speaking" });
    rerender(<VoiceConversationPanel voice={speaking} {...panelProps} />);
    await user.click(screen.getByRole("button", { name: /stop speaking/i }));
    expect(speaking.stopSpeaking).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /i.m done talking/i })).not.toBeInTheDocument();
  });

  it("shows what was heard and the answer, and ends on request", async () => {
    const voice = fake({ phase: "listening", heard: "explain program two", answer: "Program 2 adds numbers." });
    const user = userEvent.setup();
    render(<VoiceConversationPanel voice={voice} {...panelProps} />);
    expect(screen.getByText(/explain program two/)).toBeInTheDocument();
    expect(screen.getByText(/program 2 adds numbers/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /end conversation/i }));
    expect(voice.end).toHaveBeenCalled();
  });

  it("shows an error with Try again / Close, and a notice", async () => {
    const voice = fake({ phase: "error", error: "The AI model server cannot be reached.", notice: "I didn't catch that." });
    const user = userEvent.setup();
    render(<VoiceConversationPanel voice={voice} {...panelProps} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/cannot be reached/);
    expect(screen.getByText(/i didn't catch that/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(voice.retry).toHaveBeenCalled();
  });

  it("controls spoken answers and speed", async () => {
    const onSpeak = vi.fn();
    const onRate = vi.fn();
    const user = userEvent.setup();
    render(
      <VoiceConversationPanel
        voice={fake({ phase: "listening" })}
        speakAnswers
        onSpeakAnswersChange={onSpeak}
        speechRate={1}
        onSpeechRateChange={onRate}
      />
    );
    await user.click(screen.getByRole("checkbox", { name: /speak answers/i }));
    expect(onSpeak).toHaveBeenCalledWith(false);
    await user.selectOptions(screen.getByLabelText(/speaking speed/i), "1.5");
    expect(onRate).toHaveBeenCalledWith(1.5);
  });

  it("is honest that it is turn-based", () => {
    render(<VoiceConversationPanel voice={fake({ phase: "listening" })} {...panelProps} />);
    expect(screen.getByText(/turn-based/i)).toBeInTheDocument();
  });
});
