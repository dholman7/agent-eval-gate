import { expect, expectStatus, test, uniqueName, type Document } from "../../fixtures";

test("an expired insurance certificate is flagged in the vendor list", { tag: "@UI-05" }, async ({ page, pages, signIn, apiAs, factory }) => {
  // Arrange: an insurance certificate that expired on 2020-01-31, extracted
  const member = await apiAs("member");
  const vendor = await factory.vendor({ name: uniqueName("Lapsed Cover") });
  const certificate = "Insurer: Harbor Mutual\nPolicy Number: HM-1\nCoverage Amount: $1,000,000\nExpiry Date: 2020-01-31\n";
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
  await pages.vendors.goto();

  // Act
  await pages.vendors.search.fill(vendor.name);

  // Assert
  const row = pages.vendors.rows.filter({ has: pages.vendors.link(vendor.name) });
  await expect(row.getByText("Insurance expired")).toBeVisible();
});
