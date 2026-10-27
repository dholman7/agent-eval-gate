import { expect, test, uniqueName } from "../../fixtures";
import { auditActions } from "./_support";

test("create a vendor: 201, draft, audited", { tag: "@VEN-01" }, async ({ apiAs }) => {
  const member = await apiAs("member");

  const response = await member.post("/api/vendors", {
    data: { name: uniqueName("Acme Freight"), category: "logistics", contact_email: "ops@acmefreight.example" },
  });

  expect(response.status()).toBe(201);
  const vendor = await response.json();
  expect(vendor.status).toBe("draft");
  expect(await auditActions(member, vendor.id)).toEqual(["vendor.created"]);
});
