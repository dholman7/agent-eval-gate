import { expect, test, uniqueName } from "../../fixtures";

test("a search that matches nothing says so", { tag: "@UI-02" }, async ({ page, pages, signIn }) => {
  // Arrange
  await signIn("member");
  await pages.vendors.goto();

  // Act
  await pages.vendors.search.fill(uniqueName("No Such Vendor"));

  // Assert
  await expect(page.getByText("No vendors match these filters.")).toBeVisible();
});
