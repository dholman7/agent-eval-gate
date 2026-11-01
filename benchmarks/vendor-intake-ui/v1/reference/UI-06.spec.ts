import { expect, expectStatus, test, type Document } from "../../fixtures";

test("insurance expiring within 30 days is flagged on the vendor page", { tag: "@UI-06" }, async ({ page, pages, signIn, apiAs, factory }) => {
  // Arrange: an insurance certificate expiring 10 days from today, extracted
  const member = await apiAs("member");
  const vendor = await factory.vendor();
  const expiry = new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const certificate = `Insurer: Harbor Mutual\nPolicy Number: HM-2\nCoverage Amount: $1,000,000\nExpiry Date: ${expiry}\n`;
  await expectStatus(
    await member.post(`/api/vendors/${vendor.id}/documents`, {
      multipart: { kind: "insurance_certificate", file: { name: "insurance.txt", mimeType: "text/plain", buffer: Buffer.from(certificate) } },
    }),
    201,
  );
  await expect
    .poll(async () => (await expectStatus<Document[]>(await member.get(`/api/vendors/${vendor.id}/documents`), 200))[0]?.status)
    .toBe("extracted");
  await signIn("member");

  // Act
  await pages.vendor.goto(vendor.id);

  // Assert
  await expect(page.getByText("Insurance expires within 30 days")).toBeVisible();
});
