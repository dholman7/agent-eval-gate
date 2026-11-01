import { expect, test } from "../../fixtures";

test("requesting changes needs a note", { tag: "@UI-04" }, async ({ pages, signIn, factory }) => {
  // Arrange
  const { vendor } = await factory.vendorInReview();
  await signIn("reviewer");
  await pages.reviewQueue.goto();
  const card = pages.reviewQueue.card(vendor.name);

  // Act: open the form and send it back without a note
  await card.getByRole("button", { name: "Request changes to W-9" }).click();
  await card.getByRole("button", { name: "Send back to member" }).click();

  // Assert
  await expect(card.getByRole("alert")).toHaveText("Add a note so the member knows what to fix.");
  await expect(card).toBeVisible();
});
