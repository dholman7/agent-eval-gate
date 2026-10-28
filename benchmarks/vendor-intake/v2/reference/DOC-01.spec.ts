import { expect, test } from "../../fixtures";
import { auditActions, createVendor, insurance, upload } from "./_support";

test("upload a document: 201, processing, audited", { tag: "@DOC-01" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await createVendor(member);

  const response = await upload(member, vendor.id, "insurance_certificate", insurance(), "insurance_certificate.txt");

  expect(response.status()).toBe(201);
  expect((await response.json()).status).toBe("processing");
  expect(await auditActions(member, vendor.id)).toContain("document.uploaded");
});
