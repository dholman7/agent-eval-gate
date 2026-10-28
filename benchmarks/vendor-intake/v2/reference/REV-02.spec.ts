import { expect, test } from "../../fixtures";
import { W9, createVendor, uploadAndExtract } from "./_support";

test("submitting with missing documents lists what is missing", { tag: "@REV-02" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await createVendor(member);
  await uploadAndExtract(member, vendor.id, "w9", W9);

  const response = await member.post(`/api/vendors/${vendor.id}/submit`);

  expect(response.status()).toBe(409);
  const error = (await response.json()).error;
  expect(error.code).toBe("documents_incomplete");
  expect([...error.missing_kinds].sort()).toEqual(["contract", "insurance_certificate"]);
});
