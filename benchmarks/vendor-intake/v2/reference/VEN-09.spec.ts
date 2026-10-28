import { expect, test } from "../../fixtures";
import { inReviewVendor } from "./_support";

test("a vendor under review cannot be edited", { tag: "@VEN-09" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await inReviewVendor(member);

  const response = await member.patch(`/api/vendors/${vendor.id}`, { data: { contact_email: "billing@acmefreight.example" } });

  expect(response.status()).toBe(409);
  expect((await response.json()).error.code).toBe("vendor_locked");
});
