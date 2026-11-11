import { expect, test } from "../../fixtures";
import { createVendor, extractions, insurance, uploadAndExtract } from "./_support";

test("an unparseable expiry date gets a null value and low confidence", { tag: "@DOC-03" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await createVendor(member);

  await uploadAndExtract(member, vendor.id, "insurance_certificate", insurance("next spring"));

  const expiry = (await extractions(member, vendor.id)).insurance_certificate.fields.expiry_date;
  expect(expiry.value).toBeNull();
  expect(expiry.confidence).toBeLessThan(0.5);
});
