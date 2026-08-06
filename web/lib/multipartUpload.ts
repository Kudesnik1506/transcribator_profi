export type PartRange = {
  partNumber: number;
  start: number;
  end: number;
};

export function computeParts(fileSize: number, partSize: number): PartRange[] {
  const parts: PartRange[] = [];
  let start = 0;
  let partNumber = 1;
  while (start < fileSize) {
    const end = Math.min(start + partSize, fileSize);
    parts.push({ partNumber, start, end });
    start = end;
    partNumber += 1;
  }
  return parts;
}

export function missingParts(allParts: PartRange[], uploadedPartNumbers: Set<number>): PartRange[] {
  return allParts.filter((part) => !uploadedPartNumbers.has(part.partNumber));
}

export function fileFingerprint(file: { name: string; size: number; lastModified: number }): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

export type PendingUpload = {
  fingerprint: string;
  uploadId: string;
  s3Key: string;
  partSize: number;
};

const STORAGE_KEY = "transcribator:pendingUpload";

export function savePendingUpload(upload: PendingUpload): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(upload));
}

export function loadPendingUpload(): PendingUpload | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PendingUpload;
  } catch {
    return null;
  }
}

export function clearPendingUpload(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export type UploadSession = {
  uploadId: string;
  s3Key: string;
  partSize: number;
  alreadyUploaded: Map<number, string>;
};

export async function resolveUploadSession(
  file: File,
  api: {
    createMultipartUpload: (filename: string, contentType: string, sizeBytes: number) => Promise<CreateMultipartUploadResult>;
    getUploadedParts: (uploadId: string, s3Key: string) => Promise<{ part_number: number; etag: string }[]>;
  }
): Promise<UploadSession> {
  const fingerprint = fileFingerprint(file);
  const pending = loadPendingUpload();

  if (pending && pending.fingerprint === fingerprint) {
    const uploaded = await api.getUploadedParts(pending.uploadId, pending.s3Key);
    return {
      uploadId: pending.uploadId,
      s3Key: pending.s3Key,
      partSize: pending.partSize,
      alreadyUploaded: new Map(uploaded.map((p) => [p.part_number, p.etag])),
    };
  }

  const created = await api.createMultipartUpload(file.name, file.type, file.size);
  savePendingUpload({
    fingerprint,
    uploadId: created.upload_id,
    s3Key: created.s3_key,
    partSize: created.part_size,
  });
  return {
    uploadId: created.upload_id,
    s3Key: created.s3_key,
    partSize: created.part_size,
    alreadyUploaded: new Map(),
  };
}

type CreateMultipartUploadResult = {
  upload_id: string;
  s3_key: string;
  part_size: number;
};
