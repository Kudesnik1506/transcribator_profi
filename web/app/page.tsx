"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createRecording, presignUpload, uploadToS3 } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) return;
    setStatus("uploading");
    setErrorMessage(null);
    try {
      const { upload_url, s3_key } = await presignUpload(file.name, file.type);
      await uploadToS3(upload_url, file);
      const recording = await createRecording(s3_key, file.name);
      router.push(`/recordings/${recording.id}`);
    } catch (error) {
      setStatus("error");
      setErrorMessage(error instanceof Error ? error.message : "Не удалось загрузить файл");
    }
  }

  return (
    <div className="flex flex-col flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-xl flex-col items-center gap-6 rounded-2xl bg-white p-10 shadow-sm dark:bg-zinc-900">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Транскрибатор</h1>
        <p className="text-center text-zinc-600 dark:text-zinc-400">
          Загрузите аудио или видео — получите Транскрипт и Сводку.
        </p>
        <input
          type="file"
          accept="audio/*,video/*"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="w-full text-sm text-zinc-700 dark:text-zinc-300"
        />
        <button
          onClick={handleUpload}
          disabled={!file || status === "uploading"}
          className="w-full rounded-full bg-foreground px-5 py-3 text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
        >
          {status === "uploading" ? "Загрузка…" : "Загрузить"}
        </button>
        {errorMessage && <p className="text-sm text-red-600">{errorMessage}</p>}
      </main>
    </div>
  );
}
