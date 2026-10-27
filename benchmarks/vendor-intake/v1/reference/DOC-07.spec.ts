import { expect, test, uniqueName } from "../../fixtures";
import { W9, createVendor, upload } from "./_support";

test("documents from another tenant are invisible", { tag: "@DOC-07" }, async ({ apiAs }) => {
  const other = await apiAs("otherTenant");
  const vendor = await createVendor(other, uniqueName("Globex Only"));
  const document = await (await upload(other, vendor.id, "w9", W9, "w9.txt")).json();

  const response = await (await apiAs("member")).get(`/api/documents/${document.id}`);

  expect(response.status()).toBe(404);
  expect((await response.json()).error.code).toBe("document_not_found");
});
