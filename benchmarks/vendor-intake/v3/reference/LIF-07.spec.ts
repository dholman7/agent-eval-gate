import { expect, test } from "../../fixtures";
import { decide, extractions, inReviewVendor, insurance, isoDaysFromToday } from "./_support";

test("a certificate that expires today can still be approved", { tag: "@LIF-07" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const reviewer = await apiAs("reviewer");
  const vendor = await inReviewVendor(member, { insurance: insurance(isoDaysFromToday(0)) });
  const certificate = (await extractions(member, vendor.id)).insurance_certificate;

  const response = await decide(reviewer, certificate.id, "approve");

  expect(response.status(), await response.text()).toBe(200);
  expect((await response.json()).status).toBe("approved");
});
