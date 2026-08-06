const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

async function apiFetch<T>(path: string, label: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
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

export function createRecording(s3Key: string, originalFilename: string): Promise<{ id: string; status: string }> {
  return postJson("/recordings", "create recording", { s3_key: s3Key, original_filename: originalFilename });
}

export function getRecording(id: string): Promise<RecordingDetail> {
  return apiFetch<RecordingDetail>(`/recordings/${id}`, "get recording");
}

export function listRecordings(): Promise<RecordingListItem[]> {
  return apiFetch<RecordingListItem[]>("/recordings", "list recordings");
}

export function retryRecording(id: string): Promise<{ id: string; status: string }> {
  return apiFetch(`/recordings/${id}/retry`, "retry recording", { method: "POST" });
}
