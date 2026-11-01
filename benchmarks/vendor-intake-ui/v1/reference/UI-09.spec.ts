import { expect, test, uniqueName } from "../../fixtures";

test("the review queue shows the lowest-confidence vendor first", { tag: "@UI-09" }, async ({ page, pages, signIn, factory }) => {
  // Arrange: two vendors in review; one has an insurance expiry date that couldn't be read
  const { vendor: clear } = await factory.vendorInReview({ name: uniqueName("Clear Dates") });
  const { vendor: unclear } = await factory.vendorInReview({
    name: uniqueName("Unclear Date"),
    files: { insurance_certificate: "insurance_certificate_unparseable.txt" },
  });
  await signIn("reviewer");

  // Act
  await pages.reviewQueue.goto();

  // Assert
  await expect(pages.reviewQueue.card(clear.name)).toBeVisible();
  const order = await page.getByRole("article").getByRole("heading", { level: 2 }).allTextContents();
  expect(order.indexOf(unclear.name), order.join(" | ")).toBeGreaterThanOrEqual(0);
  expect(order.indexOf(unclear.name), order.join(" | ")).toBeLessThan(order.indexOf(clear.name));
});
