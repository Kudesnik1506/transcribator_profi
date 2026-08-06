import { authHeader, clearToken } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type RecordingSegment = {
  id: string;
  start_ms: number;
  end_ms: number;
  text: string;
};

export type RecordingSummary = {
  items: string[];
};

export type RecordingDetail = {
  id: string;
  status: string;
  progress_percent: number;
  original_filename: string;
  content_type: string;
  media_url: string;
  error_message: string | null;
  segments: RecordingSegment[];
  summary: RecordingSummary | null;
};

export type RecordingListItem = {
  id: string;
  original_filename: string;
  status: string;
  progress_percent: number;
  created_at: string;
};

export type CreateMultipartUploadResponse = {
  upload_id: string;
  s3_key: string;
  part_size: number;
  part_count: number;
};

export type UploadedPartInfo = {
  part_number: number;
  etag: string;
  size: number;
};

export type PartUrlResponse = {
  upload_url: string;
};

function handleUnauthorized(response: Response): void {
  if (response.status !== 401) return;
  clearToken();
  if (typeof window !== "undefined") window.location.href = "/login";
}

async function apiFetch<T>(path: string, label: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...authHeader(), ...init?.headers },
  });
  if (!response.ok) {
    handleUnauthorized(response);
    if (response.status === 413) {
      throw new Error("файл больше допустимого размера");
    }
    throw new Error(`${label} failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json();
}

function postJson<T>(path: string, label: string, body: object): Promise<T> {
  return apiFetch<T>(path, label, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function createMultipartUpload(
  filename: string,
  contentType: string,
  sizeBytes: number
): Promise<CreateMultipartUploadResponse> {
  return postJson("/uploads/multipart", "create multipart upload", {
    filename,
    content_type: contentType,
    size_bytes: sizeBytes,
  });
}

export function getPartUploadUrl(uploadId: string, partNumber: number, s3Key: string): Promise<PartUrlResponse> {
  return postJson(`/uploads/multipart/${uploadId}/parts/${partNumber}`, "get part upload url", {
    s3_key: s3Key,
  });
}

export function getUploadedParts(uploadId: string, s3Key: string): Promise<UploadedPartInfo[]> {
  return apiFetch<UploadedPartInfo[]>(
    `/uploads/multipart/${uploadId}/parts?s3_key=${encodeURIComponent(s3Key)}`,
    "get uploaded parts"
  );
}

export function completeMultipartUpload(
  uploadId: string,
  s3Key: string,
  parts: { part_number: number; etag: string }[]
): Promise<void> {
  return postJson(`/uploads/multipart/${uploadId}/complete`, "complete multipart upload", {
    s3_key: s3Key,
    parts,
  });
}

export function abortMultipartUpload(uploadId: string, s3Key: string): Promise<void> {
  return postJson(`/uploads/multipart/${uploadId}/abort`, "abort multipart upload", { s3_key: s3Key });
}

// Timeweb S3 bucket CORS config must expose the ETag header
// (Access-Control-Expose-Headers: ETag) or the browser can read the
// upload succeeding but never see the ETag needed to complete the
// multipart upload. Verify this once real S3 credentials are available.
export function uploadPart(url: string, blob: Blob, onProgress: (loadedBytes: number) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const etag = xhr.getResponseHeader("ETag");
        if (!etag) {
          reject(new Error("часть загружена, но сервер не вернул ETag"));
          return;
        }
        resolve(etag);
      } else {
        reject(new Error(`ошибка загрузки части: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("сеть оборвалась при загрузке части"));
    xhr.send(blob);
  });
}

export function createRecording(
  s3Key: string,
  originalFilename: string,
  contentType: string
): Promise<{ id: string; status: string }> {
  return postJson("/recordings", "create recording", {
    s3_key: s3Key,
    original_filename: originalFilename,
    content_type: contentType,
  });
}

export function getRecording(id: string): Promise<RecordingDetail> {
  return apiFetch<RecordingDetail>(`/recordings/${id}`, "get recording");
}

export type ExportFormat = "txt" | "srt" | "docx";

// A plain <a href> download link can't carry the Authorization header, so
// the export endpoint (like every other recording route) requires it —
// fetch as a blob instead and trigger the browser's download via a
// throwaway object URL.
export async function downloadExport(id: string, format: ExportFormat, filenameHint: string): Promise<void> {
  const response = await fetch(`${API_URL}/recordings/${id}/export/${format}`, { headers: authHeader() });
  if (!response.ok) {
    handleUnauthorized(response);
    throw new Error(`export failed: ${response.status}`);
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const asciiMatch = disposition.match(/filename="([^"]+)"/);
  const filename = asciiMatch?.[1] ?? `${filenameHint}.${format}`;

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export type SearchMatch = {
  segment_id: string;
  start_ms: number;
  end_ms: number;
  text: string;
};

export type SearchResult = {
  query: string;
  total: number;
  matches: SearchMatch[];
};

export function searchRecording(recordingId: string, query: string): Promise<SearchResult> {
  return apiFetch<SearchResult>(
    `/recordings/${recordingId}/search?q=${encodeURIComponent(query)}`,
    "search recording"
  );
}

export function listRecordings(): Promise<RecordingListItem[]> {
  return apiFetch<RecordingListItem[]>("/recordings", "list recordings");
}

export function retryRecording(id: string): Promise<{ id: string; status: string }> {
  return apiFetch(`/recordings/${id}/retry`, "retry recording", { method: "POST" });
}

export type DialogMessage = {
  role: string;
  content: string;
  created_at: string;
};

export function getMessages(recordingId: string): Promise<DialogMessage[]> {
  return apiFetch<DialogMessage[]>(`/recordings/${recordingId}/messages`, "get messages");
}

export async function askQuestion(
  recordingId: string,
  content: string,
  onDelta: (chunk: string) => void
): Promise<void> {
  const response = await fetch(`${API_URL}/recordings/${recordingId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ content }),
  });
  if (!response.ok || !response.body) {
    handleUnauthorized(response);
    if (response.status === 413) {
      throw new Error("транскрипт не помещается в контекст модели");
    }
    if (response.status === 409) {
      throw new Error("транскрипт ещё не готов");
    }
    throw new Error(`ask question failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onDelta(decoder.decode(value, { stream: true }));
  }
}

export type CurrentUser = {
  id: string;
  email: string;
  role: string;
  status: string;
};

export async function register(email: string, password: string): Promise<{ id: string; status: string }> {
  const response = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `registration failed: ${response.status}`);
  }
  return response.json();
}

export async function login(email: string, password: string): Promise<string> {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `login failed: ${response.status}`);
  }
  const data = await response.json();
  return data.access_token as string;
}

export function getMe(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/auth/me", "get current user");
}
