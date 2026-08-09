"use client";

import { useEffect, useState } from "react";

import { askQuestion, getMessages, type DialogMessage } from "@/lib/api";

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
        {messages.map((message, index) => (
          <div key={index} className={message.role === "user" ? "self-end max-w-[80%]" : "max-w-[80%]"}>
            <p
              className={
                message.role === "user"
                  ? "rounded-2xl bg-foreground px-4 py-2 text-sm text-background"
                  : "rounded-2xl bg-zinc-100 px-4 py-2 text-sm text-black dark:bg-zinc-800 dark:text-zinc-50"
              }
            >
              {message.content}
            </p>
          </div>
        ))}
        {streamingAnswer !== null && (
          <div className="max-w-[80%]">
            <p className="rounded-2xl bg-zinc-100 px-4 py-2 text-sm text-black dark:bg-zinc-800 dark:text-zinc-50">
              {streamingAnswer || "…"}
            </p>
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
          className="rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
        >
          {sending ? "…" : "Спросить"}
        </button>
      </div>
    </section>
  );
}
