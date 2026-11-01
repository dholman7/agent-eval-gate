import { expect, test } from "../../fixtures";

test("the activity log lists what happened in order", { tag: "@UI-07" }, async ({ page, pages, signIn, factory }) => {
  // Arrange
  const vendor = await factory.vendor();
  await factory.upload(vendor.id, "w9");
  await signIn("member");

  // Act
  await pages.vendor.goto(vendor.id);

  // Assert
  const entries = page.getByRole("region", { name: "Activity" }).getByRole("listitem");
  await expect(entries.filter({ hasText: "Uploaded a document" })).toBeVisible();
  const texts = await entries.allTextContents();
  const created = texts.findIndex((t) => t.includes("Created the vendor"));
  const uploaded = texts.findIndex((t) => t.includes("Uploaded a document"));
  expect(created, texts.join(" | ")).toBeGreaterThanOrEqual(0);
  expect(created, texts.join(" | ")).toBeLessThan(uploaded);
});
