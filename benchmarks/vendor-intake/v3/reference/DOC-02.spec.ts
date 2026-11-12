import { expect, test } from "../../fixtures";
import { createVendor, extractions, insurance, uploadAndExtract } from "./_support";

test("extraction completes in the background with scored fields", { tag: "@DOC-02" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await createVendor(member);

  await uploadAndExtract(member, vendor.id, "insurance_certificate", insurance());

  const fields = (await extractions(member, vendor.id)).insurance_certificate.fields;
  expect(Object.keys(fields).sort()).toEqual(["coverage_amount", "expiry_date", "insurer", "policy_number"]);
  for (const field of Object.values(fields)) {
    expect(field.confidence).toBeGreaterThanOrEqual(0);
    expect(field.confidence).toBeLessThanOrEqual(1);
  }
});
