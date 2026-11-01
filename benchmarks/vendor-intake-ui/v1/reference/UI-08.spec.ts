import { expect, expectStatus, test, type Document } from "../../fixtures";

test("a vendor can't be submitted until every document is extracted", { tag: "@UI-08" }, async ({ pages, signIn, apiAs, factory }) => {
  // Arrange: only the W-9, extracted
  const member = await apiAs("member");
  const vendor = await factory.vendor();
  await factory.upload(vendor.id, "w9");
  await expect
    .poll(async () => (await expectStatus<Document[]>(await member.get(`/api/vendors/${vendor.id}/documents`), 200))[0]?.status)
    .toBe("extracted");
  await signIn("member");

  // Act
  await pages.vendor.goto(vendor.id);

  // Assert
  await expect(pages.vendor.stillNeeded(["insurance_certificate", "contract"])).toBeVisible();
  await expect(pages.vendor.submitButton).toBeDisabled();
});
