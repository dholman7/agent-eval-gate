import { expect, test, uniqueName } from "../../fixtures";
import { createVendor, listVendors } from "./_support";

test("a page past the last vendor is empty but still reports the total", { tag: "@LIF-15" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  // Scoped to this test's own vendors: other tests create vendors in parallel.
  const name = uniqueName("Paging Probe");
  for (const n of [1, 2, 3]) await createVendor(member, `${name} ${n}`);
  const first = await listVendors(member, { q: name, limit: 1 });

  const past = await listVendors(member, { q: name, limit: 20, offset: first.total + 50 });

  expect(first.total).toBe(3);
  expect(past.items).toEqual([]);
  expect(past.total).toBe(first.total);
});
