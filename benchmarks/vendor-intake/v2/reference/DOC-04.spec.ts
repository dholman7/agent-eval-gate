import { expect, test } from "../../fixtures";
import { createVendor, upload } from "./_support";

const TEN_MIB = 10 * 1024 * 1024;
const cases = [
  { name: "an empty file", kind: "w9", content: "", file: "empty.txt", mime: "text/plain", status: 422, code: "empty_file" },
  { name: "10 MiB + 1 byte", kind: "w9", content: "x".repeat(TEN_MIB + 1), file: "big.txt", mime: "text/plain", status: 413, code: "file_too_large" },
  { name: "an .exe file", kind: "w9", content: "MZ", file: "tool.exe", mime: "application/octet-stream", status: 415, code: "unsupported_type" },
  { name: "an unknown kind", kind: "passport", content: "text", file: "doc.txt", mime: "text/plain", status: 422, code: "validation_error" },
];

for (const c of cases) {
  test(`rejects ${c.name}`, { tag: "@DOC-04" }, async ({ apiAs }) => {
    const member = await apiAs("member");
    const vendor = await createVendor(member);

    const response = await upload(member, vendor.id, c.kind, c.content, c.file, c.mime);

    expect(response.status()).toBe(c.status);
    expect((await response.json()).error.code).toBe(c.code);
  });
}
