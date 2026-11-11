import { expect, test, uniqueName } from "../../fixtures";
import { createVendor, inReviewVendor, listVendors } from "./_support";

test("search and the status filter apply together", { tag: "@LIF-14" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const word = uniqueName("Quillon").replace(" ", "");
  await createVendor(member, `${word} Draft Supply`);
  const inReview = await inReviewVendor(member, { name: `${word} Review Supply` });

  const page = await listVendors(member, { q: word, status: "in_review" });

  expect(page.items.map((v) => v.id)).toEqual([inReview.id]);
  expect(page.total).toBe(1);
});
