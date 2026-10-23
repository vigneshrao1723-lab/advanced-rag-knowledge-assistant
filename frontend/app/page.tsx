import Link from "next/link";
import {
  ArrowRight,
  AudioLines,
  BookOpenText,
  Check,
  FileText,
  Fingerprint,
  Layers3,
  MessageSquareText,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

const capabilities = [
  {
    icon: FileText,
    title: "Bring your knowledge",
    description:
      "Upload PDF, Word, text, Markdown or CSV files and follow each document as it is processed and indexed.",
    tag: "Document ingestion",
  },
  {
    icon: Search,
    title: "Retrieve relevant evidence",
    description:
      "Combine semantic and full-text retrieval, rank the results, and keep retrieval scoped to your workspace.",
    tag: "Hybrid retrieval",
  },
  {
    icon: BookOpenText,
    title: "Answers you can inspect",
    description:
      "Get evidence-grounded responses with citations you can open to inspect the exact source text.",
    tag: "Source citations",
  },
  {
    icon: AudioLines,
    title: "Ask by voice or text",
    description:
      "Use the same knowledge workflow with typed questions or the app's offline voice input and audio playback.",
    tag: "Voice mode",
  },
];

const steps = [
  { number: "01", title: "Add documents", description: "Upload files to your private workspace." },
  { number: "02", title: "Find the evidence", description: "Search indexed content with hybrid retrieval." },
  { number: "03", title: "Ask and verify", description: "Read cited answers and inspect their sources." },
];

export default function Home() {
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-20 pb-12 pt-6 sm:gap-28 sm:pt-12">
      <section className="relative overflow-hidden rounded-[2rem] border border-slate-200 bg-[#0b1220] px-6 py-12 text-white shadow-2xl shadow-slate-900/10 sm:px-12 sm:py-16 lg:px-16 lg:py-20">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -right-24 -top-28 size-96 rounded-full bg-indigo-500/20 blur-3xl" />
          <div className="absolute -bottom-36 left-1/3 size-80 rounded-full bg-teal-400/10 blur-3xl" />
          <div className="absolute inset-0 opacity-[0.08] [background-image:linear-gradient(rgba(255,255,255,.3)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.3)_1px,transparent_1px)] [background-size:42px_42px]" />
        </div>

        <div className="relative grid items-center gap-12 lg:grid-cols-[1.1fr_.9fr]">
          <div>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-3 py-1.5 text-xs font-medium text-slate-200">
              <Sparkles className="size-3.5 text-teal-300" aria-hidden="true" />
              Knowledge, with evidence attached
            </div>
            <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">
              Your documents.
              <br />
              <span className="bg-gradient-to-r from-indigo-300 via-sky-200 to-teal-200 bg-clip-text text-transparent">
                Answers you can trust.
              </span>
            </h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-slate-300 sm:text-lg">
              Turn scattered files into a searchable knowledge workspace. Ask questions, trace every
              answer to its source, and keep your team&apos;s information in its own workspace.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/register"
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0b1220]"
              >
                Create your workspace <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
              <Link
                href="/login"
                className="inline-flex min-h-12 items-center justify-center rounded-xl border border-white/20 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
              >
                Sign in
              </Link>
            </div>
            <div className="mt-8 flex flex-wrap gap-x-5 gap-y-3 text-xs text-slate-300">
              <span className="inline-flex items-center gap-2"><Check className="size-4 text-teal-300" aria-hidden="true" /> Citation-backed answers</span>
              <span className="inline-flex items-center gap-2"><Check className="size-4 text-teal-300" aria-hidden="true" /> Workspace isolation</span>
              <span className="inline-flex items-center gap-2"><Check className="size-4 text-teal-300" aria-hidden="true" /> Local providers by default</span>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-lg">
            <div className="absolute -inset-5 rounded-[2rem] bg-gradient-to-br from-indigo-500/20 to-teal-300/10 blur-2xl" />
            <div className="relative overflow-hidden rounded-2xl border border-white/15 bg-[#111b2d]/95 shadow-2xl">
              <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
                <div className="flex items-center gap-3">
                  <div className="flex size-9 items-center justify-center rounded-xl bg-indigo-400/15 text-indigo-200">
                    <MessageSquareText className="size-4" aria-hidden="true" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold">Knowledge chat</p>
                    <p className="mt-0.5 text-xs text-slate-400">Workspace · Product handbook</p>
                  </div>
                </div>
                <span className="rounded-full border border-teal-300/20 bg-teal-300/10 px-2.5 py-1 text-[10px] font-medium text-teal-200">Evidence found</span>
              </div>
              <div className="space-y-5 p-5 sm:p-6">
                <div className="ml-auto max-w-[88%] rounded-2xl rounded-br-md bg-indigo-500/20 px-4 py-3 text-sm leading-6 text-indigo-50">
                  What is our return window, and where is that documented?
                </div>
                <div className="max-w-[96%] rounded-2xl rounded-bl-md border border-white/10 bg-white/[0.04] px-4 py-4">
                  <div className="mb-3 flex items-center gap-2 text-xs font-medium text-teal-200">
                    <Sparkles className="size-3.5" aria-hidden="true" /> Answer grounded in your files
                  </div>
                  <p className="text-sm leading-6 text-slate-200">
                    The return window is <span className="rounded bg-teal-300/10 px-1 text-teal-100">30 days from purchase</span>.
                    Check the cited policy excerpt below to verify the original wording.
                  </p>
                  <div className="mt-4 rounded-xl border border-indigo-300/20 bg-indigo-300/[0.06] p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-indigo-100">
                      <FileText className="size-4" aria-hidden="true" /> Returns-policy.pdf
                    </div>
                    <p className="mt-2 border-l-2 border-teal-300/70 pl-3 text-xs leading-5 text-slate-300">
                      “Items may be returned within thirty days of purchase…”
                    </p>
                    <p className="mt-2 text-[10px] text-slate-400">Source preview · illustrative interface preview</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-xs text-slate-400">
                  <Fingerprint className="size-4 text-teal-200" aria-hidden="true" />
                  Private workspace · Source-linked response
                </div>
              </div>
            </div>
            <p className="relative mt-3 text-center text-[11px] text-slate-400">
              Interface preview for illustration; sample content is not a live response.
            </p>
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-600">A complete knowledge workflow</p>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            More than a chat box.
          </h2>
          <p className="mt-4 text-base leading-7 text-slate-600">
            Move from raw files to traceable answers in one connected workspace.
          </p>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {capabilities.map(({ icon: Icon, title, description, tag }) => (
            <article key={title} className="group rounded-2xl border border-slate-200 bg-white p-6 transition duration-200 hover:-translate-y-1 hover:border-indigo-200 hover:shadow-xl hover:shadow-slate-900/[0.05]">
              <div className="flex size-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700 transition group-hover:bg-indigo-600 group-hover:text-white">
                <Icon className="size-5" aria-hidden="true" />
              </div>
              <p className="mt-6 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{tag}</p>
              <h3 className="mt-2 text-lg font-semibold tracking-tight text-slate-950">{title}</h3>
              <p className="mt-3 text-sm leading-6 text-slate-600">{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="grid gap-10 rounded-3xl border border-slate-200 bg-slate-50 p-6 sm:p-10 lg:grid-cols-[.8fr_1.2fr] lg:items-center lg:p-12">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-700">Simple by design</p>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            From files to clarity in three steps.
          </h2>
          <p className="mt-4 max-w-md text-sm leading-6 text-slate-600">
            Keep the workflow visible, and keep the evidence close to the answer.
          </p>
          <Link href="/register" className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-indigo-700 transition hover:text-indigo-900">
            Get started <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
        <div className="space-y-3">
          {steps.map((step) => (
            <div key={step.number} className="flex gap-4 rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-xs font-semibold text-white">{step.number}</div>
              <div>
                <h3 className="font-semibold text-slate-950">{step.title}</h3>
                <p className="mt-1 text-sm leading-6 text-slate-600">{step.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-5 rounded-3xl bg-indigo-50 p-6 sm:grid-cols-[1fr_auto] sm:items-center sm:p-9">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-indigo-800">
            <ShieldCheck className="size-5" aria-hidden="true" /> Designed for traceability
          </div>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">Keep the source one click away.</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Answers include citations, and source inspection lets you check the retrieved text. Workspace-scoped access controls help keep each team&apos;s documents separate.
          </p>
        </div>
        <Link href="/register" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-indigo-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2">
          Try the workspace <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </section>

      <footer className="flex flex-col gap-3 border-t border-slate-200 pt-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
        <span className="inline-flex items-center gap-2 font-medium text-slate-700"><Layers3 className="size-4" aria-hidden="true" /> Advanced RAG Knowledge Assistant</span>
        <span>Grounded answers. Inspectable sources. Private workspaces.</span>
      </footer>
    </div>
  );
}
