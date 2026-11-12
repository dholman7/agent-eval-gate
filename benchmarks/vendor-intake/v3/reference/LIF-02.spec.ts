import { expect, test } from "../../fixtures";
import { auditActions, decided, extractions, inReviewVendor, vendorStatus } from "./_support";

test("rejecting one document sends the whole vendor back", { tag: "@LIF-02" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const reviewer = await apiAs("reviewer");
  const vendor = await inReviewVendor(member);
  const contract = (await extractions(member, vendor.id)).contract;

  await decided(reviewer, contract.id, "reject", "Wrong counterparty");

  expect(await vendorStatus(member, vendor.id)).toBe("rejected");
  const actions = await auditActions(member, vendor.id);
  const rejected = actions.indexOf("extraction.rejected");
  expect(rejected).toBeGreaterThanOrEqual(0);
  expect(actions.indexOf("vendor.rejected")).toBeGreaterThan(rejected);
});
