import { expect, test } from "../../fixtures";
import { decide, extractions, inReviewVendor, queueItem } from "./_support";

test("an admin can review vendors", { tag: "@LIF-12" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const admin = await apiAs("admin");
  const vendor = await inReviewVendor(member);

  const item = await queueItem(admin, vendor.id);
  const response = await decide(admin, (await extractions(member, vendor.id)).w9.id, "approve");

  expect(item).toBeDefined();
  expect(response.status(), await response.text()).toBe(200);
});
