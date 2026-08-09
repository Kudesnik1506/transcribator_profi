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
  mode: string;
  progress_percent: number;
  original_filename: string;
  content_type: string;
  media_url: string | null;
  media_deleted_at: string | null;
  error_message: string | null;
  segments: RecordingSegment[];
  summary: RecordingSummary | null;
  is_owner: boolean;
  owner_email: string | null;
  can_ask: boolean;
};

export type RecordingListItem = {
  id: string;
  original_filename: string;
  status: string;
  mode: string;
  progress_percent: number;
  created_at: string;
  owner_email?: string | null;
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
    if (response.status === 429) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.detail ?? "превышен дневной лимит загрузок");
    }
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `${label} failed: ${response.status}`);
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

const MAX_PART_UPLOAD_ATTEMPTS = 3;
const PART_UPLOAD_RETRY_DELAY_MS = 2000;

class NetworkUploadError extends Error {
  constructor() {
    super("сеть оборвалась при загрузке части");
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Timeweb S3 bucket CORS config must expose the ETag header
// (Access-Control-Expose-Headers: ETag) or the browser can read the
// upload succeeding but never see the ETag needed to complete the
// multipart upload. Verify this once real S3 credentials are available.
function uploadPartOnce(url: string, blob: Blob, onProgress: (loadedBytes: number) => void): Promise<string> {
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
    xhr.onerror = () => reject(new NetworkUploadError());
    xhr.send(blob);
  });
}

// A dropped connection mid-part shouldn't force the user to manually hit
// "Продолжить загрузку" — retry transient network failures a few times
// before giving up. HTTP-status errors (expired presigned URL, etc.) go
// straight through: retrying the same URL wouldn't fix those.
export async function uploadPart(url: string, blob: Blob, onProgress: (loadedBytes: number) => void): Promise<string> {
  for (let attempt = 1; attempt <= MAX_PART_UPLOAD_ATTEMPTS; attempt++) {
    try {
      return await uploadPartOnce(url, blob, onProgress);
    } catch (error) {
      if (!(error instanceof NetworkUploadError) || attempt === MAX_PART_UPLOAD_ATTEMPTS) throw error;
      onProgress(0);
      await sleep(PART_UPLOAD_RETRY_DELAY_MS);
    }
  }
  throw new NetworkUploadError();
}

export type ProcessingMode = "fast" | "deferred";

export function createRecording(
  s3Key: string,
  originalFilename: string,
  contentType: string,
  mode: ProcessingMode
): Promise<{ id: string; status: string }> {
  return postJson("/recordings", "create recording", {
    s3_key: s3Key,
    original_filename: originalFilename,
    content_type: contentType,
    mode,
  });
}

export function getPublicConfig(): Promise<{ default_processing_mode: ProcessingMode }> {
  return apiFetch("/config", "get config");
}

export function getRecording(id: string): Promise<RecordingDetail> {
  return apiFetch<RecordingDetail>(`/recordings/${id}`, "get recording");
}

export type ExportFormat = "txt" | "srt" | "docx";

// Mirrors backend/app/export.py's _stem() — used only as a fallback when
// Content-Disposition parsing fails, so a raw original_filename like
// "meeting.mp4" doesn't turn into a double extension like "meeting.mp4.txt".
export function stemFilename(filename: string): string {
  return filename.replace(/\.[^./]+$/, "");
}

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
  const filename = asciiMatch?.[1] ?? `${stemFilename(filenameHint)}.${format}`;

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

export function listSharedRecordings(): Promise<RecordingListItem[]> {
  return apiFetch<RecordingListItem[]>("/recordings/shared-with-me", "list shared recordings");
}

export type RecordingShare = {
  id: string;
  email: string;
  can_ask: boolean;
  created_at: string;
};

export function shareRecording(recordingId: string, email: string, canAsk: boolean): Promise<RecordingShare> {
  return postJson(`/recordings/${recordingId}/shares`, "share recording", { email, can_ask: canAsk });
}

export function listShares(recordingId: string): Promise<RecordingShare[]> {
  return apiFetch<RecordingShare[]>(`/recordings/${recordingId}/shares`, "list shares");
}

export function revokeShare(recordingId: string, shareId: string): Promise<void> {
  return apiFetch<void>(`/recordings/${recordingId}/shares/${shareId}`, "revoke share", { method: "DELETE" });
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
  telegram_linked: boolean;
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

export type TelegramLinkCode = {
  code: string;
  bot_username: string;
  expires_at: string;
};

export function createTelegramLinkCode(): Promise<TelegramLinkCode> {
  return apiFetch<TelegramLinkCode>("/telegram/link-code", "create telegram link code", { method: "POST" });
}

export function unlinkTelegram(): Promise<void> {
  return apiFetch<void>("/telegram/unlink", "unlink telegram", { method: "POST" });
}

export function deleteAccount(): Promise<void> {
  return apiFetch<void>("/auth/me", "delete account", { method: "DELETE" });
}

export type AdminUser = {
  id: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
};

export function adminListUsers(): Promise<AdminUser[]> {
  return apiFetch<AdminUser[]>("/admin/users", "list users");
}

export function adminApproveUser(userId: string): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/admin/users/${userId}/approve`, "approve user", { method: "POST" });
}

export function adminBlockUser(userId: string): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/admin/users/${userId}/block`, "block user", { method: "POST" });
}

export type AdminRecording = {
  id: string;
  original_filename: string;
  status: string;
  mode: string;
  progress_percent: number;
  user_id: string | null;
  user_email: string | null;
  created_at: string;
};

export function adminListRecordings(filters: { userId?: string; status?: string }): Promise<AdminRecording[]> {
  const params = new URLSearchParams();
  if (filters.userId) params.set("user_id", filters.userId);
  if (filters.status) params.set("status", filters.status);
  const query = params.toString();
  return apiFetch<AdminRecording[]>(`/admin/recordings${query ? `?${query}` : ""}`, "list all recordings");
}

export function adminDeleteRecording(recordingId: string): Promise<void> {
  return apiFetch<void>(`/admin/recordings/${recordingId}`, "delete recording", { method: "DELETE" });
}

export type AdminErrorLog = {
  id: string;
  recording_id: string | null;
  level: string;
  message: string;
  context: Record<string, unknown>;
  created_at: string;
};

export function adminListErrorLogs(filters: { level?: string; recordingId?: string }): Promise<AdminErrorLog[]> {
  const params = new URLSearchParams();
  if (filters.level) params.set("level", filters.level);
  if (filters.recordingId) params.set("recording_id", filters.recordingId);
  const query = params.toString();
  return apiFetch<AdminErrorLog[]>(`/admin/error-logs${query ? `?${query}` : ""}`, "list error logs");
}

export type AdminActivityLog = {
  id: string;
  user_id: string | null;
  user_email: string | null;
  action: string;
  context: Record<string, unknown>;
  ip: string | null;
  user_agent: string | null;
  created_at: string;
};

export function adminListActivityLogs(filters: { userId?: string; action?: string }): Promise<AdminActivityLog[]> {
  const params = new URLSearchParams();
  if (filters.userId) params.set("user_id", filters.userId);
  if (filters.action) params.set("action", filters.action);
  const query = params.toString();
  return apiFetch<AdminActivityLog[]>(`/admin/activity${query ? `?${query}` : ""}`, "list activity logs");
}

// --- Тикеты поддержки ---

export type TicketEvent = {
  id: string;
  status: string;
  message: string;
  author: "user" | "agent";
  created_at: string;
};

export type TicketHypothesis = {
  id: string;
  text: string;
  verdict: "pending" | "rejected" | "confirmed";
  evidence: string | null;
  created_at: string;
};

export type TicketListItem = {
  id: string;
  number: number;
  description: string;
  status: string;
  created_at: string;
};

export type TicketDetail = {
  id: string;
  number: number;
  description: string;
  page_url: string | null;
  screenshot_url: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  events: TicketEvent[];
  hypotheses: TicketHypothesis[];
};

export type ScreenshotUrlResponse = {
  upload_url: string;
  s3_key: string;
};

export function createTicketScreenshotUrl(
  filename: string,
  contentType: string,
  sizeBytes: number
): Promise<ScreenshotUrlResponse> {
  return postJson("/tickets/screenshot-url", "get screenshot upload url", {
    filename,
    content_type: contentType,
    size_bytes: sizeBytes,
  });
}

// Screenshots are a single PUT (no multipart, no retry loop) — plain fetch
// is enough for a file this small.
export async function uploadScreenshot(url: string, blob: Blob, contentType: string): Promise<void> {
  const response = await fetch(url, { method: "PUT", headers: { "Content-Type": contentType }, body: blob });
  if (!response.ok) {
    throw new Error(`не удалось загрузить скриншот: ${response.status}`);
  }
}

export function createTicket(
  description: string,
  pageUrl?: string,
  screenshotS3Key?: string
): Promise<TicketDetail> {
  return postJson("/tickets", "create ticket", {
    description,
    page_url: pageUrl,
    screenshot_s3_key: screenshotS3Key,
  });
}

export function listMyTickets(): Promise<TicketListItem[]> {
  return apiFetch<TicketListItem[]>("/tickets", "list tickets");
}

export function getTicket(id: string): Promise<TicketDetail> {
  return apiFetch<TicketDetail>(`/tickets/${id}`, "get ticket");
}

export type AdminTicketListItem = TicketListItem & { user_email: string };

export type AdminActivitySnapshot = {
  action: string;
  context: Record<string, unknown>;
  created_at: string;
};

export type AdminTicketDetail = TicketDetail & {
  user_email: string;
  recent_activity: AdminActivitySnapshot[];
};

export function adminListTickets(status?: string): Promise<AdminTicketListItem[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiFetch<AdminTicketListItem[]>(`/admin/tickets${query}`, "list tickets");
}

export function adminGetTicket(id: string): Promise<AdminTicketDetail> {
  return apiFetch<AdminTicketDetail>(`/admin/tickets/${id}`, "get ticket");
}

export function adminCreateHypothesis(ticketId: string, text: string): Promise<AdminTicketDetail> {
  return postJson(`/admin/tickets/${ticketId}/hypotheses`, "create hypothesis", { text });
}

export function adminUpdateHypothesis(
  ticketId: string,
  hypothesisId: string,
  verdict: "rejected" | "confirmed",
  evidence: string
): Promise<AdminTicketDetail> {
  return apiFetch<AdminTicketDetail>(`/admin/tickets/${ticketId}/hypotheses/${hypothesisId}`, "update hypothesis", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ verdict, evidence }),
  });
}

export function adminCreateTicketEvent(ticketId: string, status: string, message: string): Promise<AdminTicketDetail> {
  return postJson(`/admin/tickets/${ticketId}/events`, "update ticket status", { status, message });
}
