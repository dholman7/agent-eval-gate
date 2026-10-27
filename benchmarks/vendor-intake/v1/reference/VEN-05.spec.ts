import { expect, test, uniqueName } from "../../fixtures";
import { createVendor, extractions, inReviewVendor } from "./_support";

test("list vendors with search, status filter, and pagination", { tag: "@VEN-05" }, async ({ apiAs }) => {
  test.setTimeout(120_000);
  const member = await apiAs("member");
  const reviewer = await apiAs("reviewer");
  const prefix = uniqueName("Paging");
  // 5 approved + 20 drafts, all sharing a prefix so other tests' vendors don't interfere.
  for (let i = 0; i < 5; i++) {
    const vendor = await inReviewVendor(member, { name: `${prefix} Freight ${i}` });
    for (const extraction of Object.values(await extractions(member, vendor.id))) {
      expect((await reviewer.post(`/api/extractions/${extraction.id}/decision`, { data: { decision: "approve" } })).status()).toBe(200);
    }
  }
  for (let i = 0; i < 20; i++) await createVendor(member, `${prefix} Draft ${i}`);

  const approved = await (await member.get("/api/vendors", { params: { q: prefix, status: "approved" } })).json();
  const lastPage = await (await member.get("/api/vendors", { params: { q: prefix, limit: 10, offset: 20 } })).json();
  const searched = await (await member.get("/api/vendors", { params: { q: "freight", limit: 100 } })).json();

  expect(approved.items).toHaveLength(5);
  expect(approved.total).toBe(5);
  expect(lastPage.items).toHaveLength(5);
  expect(lastPage.total).toBe(25);
  expect(searched.items.length).toBeGreaterThan(0);
  for (const vendor of searched.items) expect(vendor.name.toLowerCase()).toContain("freight");
});
