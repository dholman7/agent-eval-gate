import { expect, test } from "../../fixtures";
import { auditActions, extractions, inReviewVendor, vendorStatus } from "./_support";

test("rejecting needs a note and returns the vendor to the member", { tag: "@REV-06" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const reviewer = await apiAs("reviewer");
  const vendor = await inReviewVendor(member);
  const w9 = (await extractions(member, vendor.id)).w9;

  const withoutNote = await reviewer.post(`/api/extractions/${w9.id}/decision`, { data: { decision: "reject" } });
  const withNote = await reviewer.post(`/api/extractions/${w9.id}/decision`, {
    data: { decision: "reject", note: "Tax ID does not match" },
  });

  expect(withoutNote.status()).toBe(422);
  expect(withNote.status()).toBe(200);
  expect(await vendorStatus(member, vendor.id)).toBe("rejected");
  expect(await auditActions(member, vendor.id)).toContain("extraction.rejected");
});
