import { expect, test } from "../../fixtures";
import { W9, inReviewVendor, upload } from "./_support";

test("documents cannot be added to a vendor under review", { tag: "@DOC-06" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await inReviewVendor(member);

  const response = await upload(member, vendor.id, "w9", W9, "w9.txt");

  expect(response.status()).toBe(409);
  expect((await response.json()).error.code).toBe("vendor_locked");
});
