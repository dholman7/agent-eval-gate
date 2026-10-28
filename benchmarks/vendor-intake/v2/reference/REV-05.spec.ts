import { expect, test } from "../../fixtures";
import { auditActions, extractions, inReviewVendor, vendorStatus } from "./_support";

test("approving every extraction approves the vendor", { tag: "@REV-05" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const reviewer = await apiAs("reviewer");
  const vendor = await inReviewVendor(member);

  for (const extraction of Object.values(await extractions(member, vendor.id))) {
    const response = await reviewer.post(`/api/extractions/${extraction.id}/decision`, { data: { decision: "approve" } });
    expect(response.status()).toBe(200);
  }

  expect(await vendorStatus(member, vendor.id)).toBe("approved");
  expect(await auditActions(member, vendor.id)).toContain("vendor.approved");
});
