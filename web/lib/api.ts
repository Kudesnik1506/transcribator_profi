const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type PresignResponse = {
  upload_url: string;
  s3_key: string;
};

export type RecordingSegment = {
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
  error_message: string | null;
  segments: RecordingSegment[];
  summary: RecordingSummary | null;
};

async function apiFetch<T>(path: string, label: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    throw new Error(`${label} failed: ${response.status}`);
  }
  return response.json();
}

export function presignUpload(filename: string, contentType: string): Promise<PresignResponse> {
  return apiFetch<PresignResponse>("/uploads/presign", "presign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, content_type: contentType }),
  });
}

export async function uploadToS3(uploadUrl: string, file: File): Promise<void> {
  const response = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  if (!response.ok) {
    throw new Error(`upload to S3 failed: ${response.status}`);
  }
}

export function createRecording(s3Key: string, originalFilename: string): Promise<{ id: string; status: string }> {
  return apiFetch("/recordings", "create recording", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ s3_key: s3Key, original_filename: originalFilename }),
  });
}

export function getRecording(id: string): Promise<RecordingDetail> {
  return apiFetch<RecordingDetail>(`/recordings/${id}`, "get recording");
}

export function retryRecording(id: string): Promise<{ id: string; status: string }> {
  return apiFetch(`/recordings/${id}/retry`, "retry recording", { method: "POST" });
}
