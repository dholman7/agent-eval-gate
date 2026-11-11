import { expect, test, uniqueName } from "../../fixtures";
import { createVendor, listVendors } from "./_support";

test("search ignores case and matches part of a name", { tag: "@LIF-13" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await createVendor(member, uniqueName("Zephyrine Cold Storage"));

  const page = await listVendors(member, { q: "COLD stor", limit: 100 });

  expect(page.items.map((v) => v.id)).toContain(vendor.id);
});
