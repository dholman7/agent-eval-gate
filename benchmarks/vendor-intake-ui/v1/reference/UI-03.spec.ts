import { expect, test, uniqueName } from "../../fixtures";

test("page through the vendor list", { tag: "@UI-03" }, async ({ page, pages, signIn, factory }) => {
  // Arrange: more than one page of vendors, whatever else the database holds
  await Promise.all(Array.from({ length: 11 }, () => factory.vendor({ name: uniqueName("Paged") })));
  await signIn("member");
  await pages.vendors.goto();
  await expect(page.getByText(/^Showing 1–10 of \d+$/)).toBeVisible();

  // Act
  // Exact: in `next dev`, Next.js's dev-tools button also has "Next" in its name.
  await page.getByRole("button", { name: "Next", exact: true }).click();

  // Assert
  await expect(page.getByText(/^Showing 11–\d+ of \d+$/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Previous", exact: true })).toBeEnabled();
});
