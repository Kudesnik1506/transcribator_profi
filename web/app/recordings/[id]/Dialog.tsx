"use client";

import { useEffect, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";

import { askQuestion, getMessages, type DialogMessage } from "@/lib/api";

// Assistant answers come back as Markdown (see SYSTEM_PROMPT in
// backend/app/worker/dialog.py) — these overrides keep it compact enough
// for a chat bubble instead of react-markdown's default block spacing.
const markdownComponents: Components = {
  p: (props) => <p className="mb-2 last:mb-0" {...props} />,
  ul: (props) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0" {...props} />,
  ol: (props) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0" {...props} />,
  strong: (props) => <strong className="font-semibold" {...props} />,
  a: (props) => <a className="underline" target="_blank" rel="noreferrer" {...props} />,
};

function MarkdownAnswer({ content }: { content: string }) {
  return <ReactMarkdown components={markdownComponents}>{content}</ReactMarkdown>;
}

function TypingIndicator() {
  return (
    <span className="flex items-center gap-1 py-0.5" aria-label="Печатает ответ…">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400" />
    </span>
  );
}

export function Dialog({ recordingId }: { recordingId: string }) {
  const [messages, setMessages] = useState<DialogMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [streamingAnswer, setStreamingAnswer] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMessages(recordingId)
      .then(setMessages)
      .catch(() => {
        // history is a nice-to-have on load; a failed fetch shouldn't block asking new questions
      });
  }, [recordingId]);

  async function handleAsk() {
    const content = question.trim();
    if (!content || sending) return;

    setSending(true);
    setError(null);
    setQuestion("");
    setMessages((prev) => [...prev, { role: "user", content, created_at: new Date().toISOString() }]);
    setStreamingAnswer("");

    try {
      let answer = "";
      await askQuestion(recordingId, content, (chunk) => {
        answer += chunk;
        setStreamingAnswer(answer);
      });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: answer, created_at: new Date().toISOString() },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось получить ответ");
    } finally {
      setStreamingAnswer(null);
      setSending(false);
    }
  }

  return (
    <section>
      <div className="flex flex-col gap-3">
        {messages.map((message, index) =>
          message.role === "user" ? (
            <div key={index} className="self-end max-w-[80%]">
              <p className="rounded-2xl bg-foreground px-4 py-2 text-sm text-background">{message.content}</p>
            </div>
          ) : (
            <div key={index} className="max-w-[80%] rounded-2xl bg-zinc-100 px-4 py-2 text-sm text-black dark:bg-zinc-800 dark:text-zinc-50">
              <MarkdownAnswer content={message.content} />
            </div>
          )
        )}
        {streamingAnswer !== null && (
          <div className="max-w-[80%] rounded-2xl bg-zinc-100 px-4 py-2 text-sm text-black dark:bg-zinc-800 dark:text-zinc-50">
            {streamingAnswer ? <MarkdownAnswer content={streamingAnswer} /> : <TypingIndicator />}
          </div>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      <div className="mt-4 flex gap-2">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") handleAsk();
          }}
          placeholder="Спросите о записи…"
          disabled={sending}
          className="flex-1 rounded-full border border-solid border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145] dark:bg-zinc-900"
        />
        <button
          onClick={handleAsk}
          disabled={sending || !question.trim()}
          className="flex items-center justify-center rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
        >
          {sending ? (
            <span
              className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-background/40 border-t-background"
              aria-label="Отправляем…"
            />
          ) : (
            "Спросить"
          )}
        </button>
      </div>
    </section>
  );
}
