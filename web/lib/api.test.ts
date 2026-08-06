import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createMultipartUpload, stemFilename } from "./api";

describe("stemFilename", () => {
  it("drops the extension", () => {
    expect(stemFilename("meeting.mp4")).toBe("meeting");
  });

  it("drops only the last extension", () => {
    expect(stemFilename("archive.tar.gz")).toBe("archive.tar");
  });

  it("returns the name unchanged when there is no extension", () => {
    expect(stemFilename("meeting")).toBe("meeting");
  });

  it("handles unicode filenames", () => {
    expect(stemFilename("совещание 2026-08-06.mp4")).toBe("совещание 2026-08-06");
  });
});

describe("apiFetch error messages", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("surfaces the backend's friendly detail instead of a raw '<label> failed: <status>'", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => ({ detail: "хранилище S3 недоступно, попробуйте позже" }),
      })
    );

    await expect(createMultipartUpload("a.mp4", "video/mp4", 100)).rejects.toThrow(
      "хранилище S3 недоступно, попробуйте позже"
    );
  });

  it("falls back to the generic label message when the response has no JSON detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error("not json");
        },
      })
    );

    await expect(createMultipartUpload("a.mp4", "video/mp4", 100)).rejects.toThrow(
      "create multipart upload failed: 500"
    );
  });
});
