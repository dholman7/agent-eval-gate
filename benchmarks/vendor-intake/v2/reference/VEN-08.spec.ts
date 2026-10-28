import { expect, test } from "../../fixtures";
import { auditActions, createVendor } from "./_support";

test("update a draft vendor and record it", { tag: "@VEN-08" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await createVendor(member);

  const response = await member.patch(`/api/vendors/${vendor.id}`, { data: { contact_email: "billing@acmefreight.example" } });

  expect(response.status()).toBe(200);
  expect((await response.json()).contact_email).toBe("billing@acmefreight.example");
  expect((await auditActions(member, vendor.id)).at(-1)).toBe("vendor.updated");
});
