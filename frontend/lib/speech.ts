// Speaking answers aloud. A `Speaker` is deliberately tiny so a future
// realtime/streaming voice backend can be added as another implementation
// without touching the conversation logic (lib/use-voice-conversation.ts).

export interface SpeakInput {
  /** Text already prepared for speech (see lib/speakable.ts). */
  text: string;
  /** Server-synthesised audio for the same answer, used if this speaker needs a URL. */
  audioUrl?: string;
  /** 0.5-2, 1 = normal. */
  rate?: number;
}

export interface Speaker {
  readonly name: string;
  /** Resolves when speech has finished OR was cancelled; rejects only on a real failure. */
  speak(input: SpeakInput): Promise<void>;
  /** Stops immediately. Safe to call at any time. */
  cancel(): void;
}

function voicesReady(synth: SpeechSynthesis, timeoutMs = 1200): Promise<SpeechSynthesisVoice[]> {
  const existing = synth.getVoices();
  if (existing.length > 0) return Promise.resolve(existing);
  return new Promise((resolve) => {
    const finish = () => {
      synth.removeEventListener("voiceschanged", finish);
      resolve(synth.getVoices());
    };
    synth.addEventListener("voiceschanged", finish);
    setTimeout(finish, timeoutMs);
  });
}

/** Prefers a voice that runs on this computer (`localService`) in the page's
 * language; hosted voices (e.g. some Chrome "Google" voices) send the text to a
 * server, which this app avoids by default. */
export function pickVoice(voices: SpeechSynthesisVoice[], lang: string): SpeechSynthesisVoice | null {
  const base = lang.toLowerCase().split("-")[0];
  const sameLanguage = voices.filter((v) => v.lang.toLowerCase().startsWith(base));
  return sameLanguage.find((v) => v.localService) ?? null;
}

export class BrowserSpeaker implements Speaker {
  readonly name = "browser";
  private cancelCurrent: (() => void) | null = null;

  static isSupported(): boolean {
    return (
      typeof window !== "undefined" &&
      "speechSynthesis" in window &&
      typeof window.SpeechSynthesisUtterance === "function"
    );
  }

  /** True when a voice that stays on this computer exists. */
  static async hasLocalVoice(lang: string): Promise<boolean> {
    if (!BrowserSpeaker.isSupported()) return false;
    return pickVoice(await voicesReady(window.speechSynthesis), lang) !== null;
  }

  async speak({ text, rate = 1 }: SpeakInput): Promise<void> {
    const synth = window.speechSynthesis;
    const lang = document.documentElement.lang || navigator.language || "en";
    const voice = pickVoice(await voicesReady(synth), lang);
    if (!voice) throw new Error("No local speech voice is available.");
    this.cancel();
    await new Promise<void>((resolve, reject) => {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.voice = voice;
      utterance.lang = voice.lang;
      utterance.rate = rate;
      let settled = false;
      const done = (error?: Error) => {
        if (settled) return;
        settled = true;
        this.cancelCurrent = null;
        if (error) reject(error);
        else resolve();
      };
      utterance.onend = () => done();
      // Cancelling fires "interrupted"/"canceled": that is a normal stop.
      utterance.onerror = (event) =>
        event.error === "interrupted" || event.error === "canceled"
          ? done()
          : done(new Error(`Speech failed: ${event.error}`));
      this.cancelCurrent = () => {
        synth.cancel();
        done();
      };
      synth.speak(utterance);
    });
  }

  cancel(): void {
    this.cancelCurrent?.();
  }
}

/** Plays audio the server synthesised (espeak): robotic but always available. */
export class ServerAudioSpeaker implements Speaker {
  readonly name = "server";
  private audio: HTMLAudioElement | null = null;
  private cancelCurrent: (() => void) | null = null;

  async speak({ audioUrl, rate = 1 }: SpeakInput): Promise<void> {
    if (!audioUrl) throw new Error("No audio is available for this answer.");
    this.cancel();
    const audio = new Audio(audioUrl);
    audio.playbackRate = rate;
    this.audio = audio;
    await new Promise<void>((resolve, reject) => {
      let settled = false;
      const done = (error?: Error) => {
        if (settled) return;
        settled = true;
        this.cancelCurrent = null;
        if (error) reject(error);
        else resolve();
      };
      audio.onended = () => done();
      audio.onerror = () => done(new Error("The answer's audio could not be played."));
      this.cancelCurrent = () => {
        audio.pause();
        done();
      };
      audio.play().catch((error: unknown) => done(error instanceof Error ? error : new Error("Playback blocked.")));
    });
  }

  cancel(): void {
    this.cancelCurrent?.();
    this.audio = null;
  }
}
