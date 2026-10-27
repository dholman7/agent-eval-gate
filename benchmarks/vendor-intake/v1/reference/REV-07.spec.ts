import { expect, test } from "../../fixtures";
import { extractions, inReviewVendor, insurance, isoDaysFromToday } from "./_support";

test("an expired insurance certificate cannot be approved", { tag: "@REV-07" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await inReviewVendor(member, { insurance: insurance(isoDaysFromToday(-1)) });
  const certificate = (await extractions(member, vendor.id)).insurance_certificate;

  const response = await (await apiAs("reviewer")).post(`/api/extractions/${certificate.id}/decision`, {
    data: { decision: "approve" },
  });

  expect(response.status()).toBe(409);
  expect((await response.json()).error.code).toBe("insurance_expired");
});
