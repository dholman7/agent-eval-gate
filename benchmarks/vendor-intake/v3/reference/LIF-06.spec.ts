import { expect, test } from "../../fixtures";
import { W9, auditActions, decided, queueItem, sentBackVendor, uploadAndExtract, vendorStatus } from "./_support";

test("approving the replacement approves a vendor whose other documents were already approved", { tag: "@LIF-06" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const reviewer = await apiAs("reviewer");
  const vendor = await sentBackVendor(member, reviewer, "w9", ["insurance_certificate", "contract"]);
  await uploadAndExtract(member, vendor.id, "w9", W9.replace("Acme Freight LLC", "Acme Freight Holdings LLC"));
  const submitted = await member.post(`/api/vendors/${vendor.id}/submit`);
  expect(submitted.status(), await submitted.text()).toBe(200);
  const pending = (await queueItem(reviewer, vendor.id))?.extractions ?? [];
  expect(pending.map((e) => e.kind)).toEqual(["w9"]);

  await decided(reviewer, pending[0].id, "approve");

  expect(await vendorStatus(member, vendor.id)).toBe("approved");
  expect(await auditActions(member, vendor.id)).toContain("vendor.approved");
});
