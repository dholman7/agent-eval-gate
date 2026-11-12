import { expect, test } from "../../fixtures";
import { decide, extractions, sentBackVendor } from "./_support";

test("once a vendor is sent back, its other documents cannot be decided", { tag: "@LIF-03" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const reviewer = await apiAs("reviewer");
  const vendor = await sentBackVendor(member, reviewer, "w9");
  const contract = (await extractions(member, vendor.id)).contract;

  const response = await decide(reviewer, contract.id, "approve");

  expect(response.status(), await response.text()).toBe(409);
  expect((await response.json()).error.code).toBe("vendor_not_in_review");
});
