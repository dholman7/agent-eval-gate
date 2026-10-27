import { expect, test } from "../../fixtures";
import { createVendor, upload } from "./_support";

test("a file of exactly 10 MiB is accepted", { tag: "@DOC-05" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await createVendor(member);

  const response = await upload(member, vendor.id, "contract", "x".repeat(10 * 1024 * 1024), "contract.txt");

  expect(response.status()).toBe(201);
});
