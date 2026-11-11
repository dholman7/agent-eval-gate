import { expect, test, uniqueName } from "../../fixtures";
import { createVendor } from "./_support";

test("vendor names are unique within a tenant, ignoring case", { tag: "@VEN-03" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const name = uniqueName("Acme Freight");
  await createVendor(member, name);

  const response = await member.post("/api/vendors", {
    data: { name: name.toLowerCase(), category: "logistics", contact_email: "ops@acmefreight.example" },
  });

  expect(response.status()).toBe(409);
  expect((await response.json()).error.code).toBe("vendor_name_taken");
});
