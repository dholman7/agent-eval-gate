import { expect, test } from "../../fixtures";
import { auditActions, readyVendor } from "./_support";

test("submit a vendor with all documents extracted", { tag: "@REV-01" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await readyVendor(member);

  const response = await member.post(`/api/vendors/${vendor.id}/submit`);

  expect(response.status()).toBe(200);
  expect((await response.json()).status).toBe("in_review");
  expect((await auditActions(member, vendor.id)).at(-1)).toBe("vendor.submitted");
});
