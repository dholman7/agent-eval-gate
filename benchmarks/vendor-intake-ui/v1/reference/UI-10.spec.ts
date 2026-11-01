import { expect, test } from "../../fixtures";

test("an uploaded document can be replaced", { tag: "@UI-10" }, async ({ page, pages, signIn, factory }) => {
  // Arrange
  const vendor = await factory.vendor();
  await factory.upload(vendor.id, "w9");
  await signIn("member");

  // Act
  await pages.vendor.goto(vendor.id);

  // Assert
  await expect(page.getByText("Replace W-9", { exact: true })).toBeVisible();
  await expect(page.getByText("Upload Contract", { exact: true })).toBeVisible();
});
