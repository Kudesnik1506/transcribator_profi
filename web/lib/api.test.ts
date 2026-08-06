import { describe, expect, it } from "vitest";

import { stemFilename } from "./api";

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
