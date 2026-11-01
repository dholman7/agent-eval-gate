import { expect, test, uniqueName } from "../../fixtures";

test("filter the vendor list by status", { tag: "@UI-01" }, async ({ page, pages, signIn, factory }) => {
  // Arrange
  const draft = await factory.vendor({ name: uniqueName("Draft Filter") });
  const { vendor: inReview } = await factory.vendorInReview({ name: uniqueName("Review Filter") });
  await signIn("member");
  await pages.vendors.goto();

  // Act
  await page.getByLabel("Status", { exact: true }).selectOption({ label: "In review" });

  // Assert
  await expect(pages.vendors.link(inReview.name)).toBeVisible();
  await expect(pages.vendors.link(draft.name)).toBeHidden();
  await expect(page).toHaveURL(/status=in_review/);
});
