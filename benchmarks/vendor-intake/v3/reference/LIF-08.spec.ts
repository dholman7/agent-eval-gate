import { expect, test } from "../../fixtures";
import { decide, extractions, inReviewVendor, insurance } from "./_support";

test("a certificate whose expiry date could not be read cannot be approved", { tag: "@LIF-08" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const reviewer = await apiAs("reviewer");
  const vendor = await inReviewVendor(member, { insurance: insurance("next spring") });
  const certificate = (await extractions(member, vendor.id)).insurance_certificate;

  const response = await decide(reviewer, certificate.id, "approve");

  expect(response.status(), await response.text()).toBe(409);
  expect((await response.json()).error.code).toBe("insurance_expiry_missing");
  expect((await extractions(member, vendor.id)).insurance_certificate.status).toBe("pending_review");
});
