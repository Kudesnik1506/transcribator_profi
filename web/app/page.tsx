"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  abortMultipartUpload,
  completeMultipartUpload,
  createMultipartUpload,
  createRecording,
  getPartUploadUrl,
  getPublicConfig,
  getUploadedParts,
  uploadPart,
  type ProcessingMode,
} from "@/lib/api";
import { clearPendingUpload, computeParts, loadPendingUpload, missingParts, resolveUploadSession } from "@/lib/multipartUpload";
import { AuthGuard } from "@/components/AuthGuard";
import { clearToken } from "@/lib/auth";
import { formatBytes } from "@/lib/format";

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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const [state, setState] = useState<UploadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [progressPercent, setProgressPercent] = useState(0);
  const [mode, setMode] = useState<ProcessingMode>("deferred");

  useEffect(() => {
    getPublicConfig()
      .then((config) => setMode(config.default_processing_mode))
      .catch(() => {
        // config fetch failing isn't fatal — "deferred" is already a sane default
      });
  }, []);

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

      const recording = await createRecording(session.s3Key, file.name, file.type, mode);
      router.push(`/recordings/${recording.id}`);
    } catch (error) {
      setState("error");
      setErrorMessage(error instanceof Error ? error.message : "Не удалось загрузить файл");
    }
  }

  function handleFiles(fileList: FileList | null) {
    setFile(fileList?.[0] ?? null);
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
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setIsDragActive(true);
          }}
          onDragLeave={() => setIsDragActive(false)}
          onDrop={(event) => {
            event.preventDefault();
            setIsDragActive(false);
            handleFiles(event.dataTransfer.files);
          }}
          className={[
            "flex w-full cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
            isDragActive
              ? "border-foreground bg-black/[.04] dark:bg-white/[.06]"
              : "border-black/[.15] dark:border-white/[.2]",
            state === "uploading" ? "pointer-events-none opacity-50" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <svg
            className="h-8 w-8 text-zinc-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775 5.25 5.25 0 0 1 10.233-2.33 3 3 0 0 1 3.758 3.848A3.752 3.752 0 0 1 18 19.5H6.75Z"
            />
          </svg>
          {file ? (
            <>
              <p className="font-medium text-black dark:text-zinc-50">{file.name}</p>
              <p className="text-sm text-zinc-500">{formatBytes(file.size)} — нажмите, чтобы выбрать другой файл</p>
            </>
          ) : (
            <>
              <p className="font-medium text-black dark:text-zinc-50">Нажмите или перетащите файл сюда</p>
              <p className="text-sm text-zinc-500">Аудио или видео</p>
            </>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*,video/*"
            onChange={(event) => handleFiles(event.target.files)}
            disabled={state === "uploading"}
            className="hidden"
          />
        </div>

        <div className="flex w-full flex-col gap-2">
          <label className="flex items-start gap-2 rounded-lg border border-solid border-black/[.08] p-3 text-sm dark:border-white/[.145]">
            <input
              type="radio"
              name="mode"
              checked={mode === "deferred"}
              onChange={() => setMode("deferred")}
              disabled={state === "uploading"}
              className="mt-0.5"
            />
            <span>
              <span className="font-medium text-black dark:text-zinc-50">В фоне (дешевле)</span>
              <br />
              <span className="text-zinc-500">Готово в течение суток, распознавание вчетверо дешевле.</span>
            </span>
          </label>
          <label className="flex items-start gap-2 rounded-lg border border-solid border-black/[.08] p-3 text-sm dark:border-white/[.145]">
            <input
              type="radio"
              name="mode"
              checked={mode === "fast"}
              onChange={() => setMode("fast")}
              disabled={state === "uploading"}
              className="mt-0.5"
            />
            <span>
              <span className="font-medium text-black dark:text-zinc-50">Сейчас</span>
              <br />
              <span className="text-zinc-500">Готово примерно за 30 минут, полная цена распознавания.</span>
            </span>
          </label>
        </div>

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
          <Link href="/profile" className="text-sm text-zinc-500 underline">
            Профиль
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
