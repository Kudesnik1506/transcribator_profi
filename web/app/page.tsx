"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  abortMultipartUpload,
  completeMultipartUpload,
  createMultipartUpload,
  createRecording,
  getPartUploadUrl,
  getUploadedParts,
  uploadPart,
} from "@/lib/api";
import { clearPendingUpload, computeParts, loadPendingUpload, missingParts, resolveUploadSession } from "@/lib/multipartUpload";
import { AuthGuard } from "@/components/AuthGuard";
import { clearToken } from "@/lib/auth";

type UploadState = "idle" | "uploading" | "error";

export default function UploadPage() {
  return (
    <AuthGuard>
      <UploadPageContent />
    </AuthGuard>
  );
}

function UploadPageContent() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<UploadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [progressPercent, setProgressPercent] = useState(0);

  async function handleUpload() {
    if (!file) return;
    setState("uploading");
    setErrorMessage(null);

    try {
      const session = await resolveUploadSession(file, { createMultipartUpload, getUploadedParts });
      const allParts = computeParts(file.size, session.partSize);
      const remaining = missingParts(allParts, new Set(session.alreadyUploaded.keys()));

      const uploadedBytesByPart = new Map<number, number>();
      for (const part of allParts) {
        if (session.alreadyUploaded.has(part.partNumber)) {
          uploadedBytesByPart.set(part.partNumber, part.end - part.start);
        }
      }

      const reportProgress = () => {
        const totalUploaded = Array.from(uploadedBytesByPart.values()).reduce((a, b) => a + b, 0);
        setProgressPercent(Math.round((totalUploaded / file.size) * 100));
      };
      reportProgress();

      const completedParts: { part_number: number; etag: string }[] = allParts
        .filter((p) => session.alreadyUploaded.has(p.partNumber))
        .map((p) => ({ part_number: p.partNumber, etag: session.alreadyUploaded.get(p.partNumber)! }));

      for (const part of remaining) {
        const { upload_url } = await getPartUploadUrl(session.uploadId, part.partNumber, session.s3Key);
        const blob = file.slice(part.start, part.end);
        const etag = await uploadPart(upload_url, blob, (loaded) => {
          uploadedBytesByPart.set(part.partNumber, loaded);
          reportProgress();
        });
        uploadedBytesByPart.set(part.partNumber, part.end - part.start);
        reportProgress();
        completedParts.push({ part_number: part.partNumber, etag });
      }

      completedParts.sort((a, b) => a.part_number - b.part_number);
      await completeMultipartUpload(session.uploadId, session.s3Key, completedParts);
      clearPendingUpload();

      const recording = await createRecording(session.s3Key, file.name, file.type);
      router.push(`/recordings/${recording.id}`);
    } catch (error) {
      setState("error");
      setErrorMessage(error instanceof Error ? error.message : "Не удалось загрузить файл");
    }
  }

  async function handleCancel() {
    const pending = loadPendingUpload();
    if (pending) {
      try {
        await abortMultipartUpload(pending.uploadId, pending.s3Key);
      } catch {
        // best-effort cleanup — an orphaned multipart upload is a bucket
        // lifecycle rule's job, not something to block the UI on
      }
      clearPendingUpload();
    }
    setFile(null);
    setState("idle");
    setProgressPercent(0);
    setErrorMessage(null);
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
          disabled={state === "uploading"}
          className="w-full text-sm text-zinc-700 dark:text-zinc-300"
        />

        {state === "uploading" && (
          <div className="w-full">
            <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
              <div
                className="h-full rounded-full bg-foreground transition-all"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <p className="mt-1 text-right text-xs text-zinc-500">{progressPercent}%</p>
          </div>
        )}

        <div className="flex w-full gap-3">
          <button
            onClick={handleUpload}
            disabled={!file || state === "uploading"}
            className="flex-1 rounded-full bg-foreground px-5 py-3 text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
          >
            {state === "uploading" ? "Загрузка…" : errorMessage ? "Продолжить загрузку" : "Загрузить"}
          </button>
          {(state === "uploading" || errorMessage) && (
            <button
              onClick={handleCancel}
              className="rounded-full border border-solid border-black/[.08] px-5 py-3 transition-colors hover:bg-black/[.04] dark:border-white/[.145] dark:hover:bg-[#1a1a1a]"
            >
              Отмена
            </button>
          )}
        </div>

        {errorMessage && <p className="text-sm text-red-600">{errorMessage}</p>}
        <div className="flex gap-4">
          <Link href="/recordings" className="text-sm text-zinc-500 underline">
            Мои Записи
          </Link>
          <button
            onClick={() => {
              clearToken();
              router.push("/login");
            }}
            className="text-sm text-zinc-500 underline"
          >
            Выйти
          </button>
        </div>
      </main>
    </div>
  );
}
