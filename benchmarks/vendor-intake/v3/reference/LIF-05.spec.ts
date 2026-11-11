import { expect, test } from "../../fixtures";
import { W9, queueItem, sentBackVendor, uploadAndExtract, vendorStatus } from "./_support";

test("after a replacement, only the new document waits for review", { tag: "@LIF-05" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const reviewer = await apiAs("reviewer");
  const vendor = await sentBackVendor(member, reviewer, "w9", ["insurance_certificate", "contract"]);

  await uploadAndExtract(member, vendor.id, "w9", W9.replace("Acme Freight LLC", "Acme Freight Holdings LLC"));
  const submitted = await member.post(`/api/vendors/${vendor.id}/submit`);
  expect(submitted.status(), await submitted.text()).toBe(200);

  expect(await vendorStatus(member, vendor.id)).toBe("in_review");
  const item = await queueItem(reviewer, vendor.id);
  expect(item?.extractions.map((e) => e.kind)).toEqual(["w9"]);
});
