import { expect, test, uniqueName } from "../../fixtures";
import { createVendor } from "./_support";

test("the same vendor name is allowed in another tenant", { tag: "@VEN-04" }, async ({ apiAs }) => {
  const name = uniqueName("Acme Freight");
  await createVendor(await apiAs("otherTenant"), name);

  const response = await (await apiAs("member")).post("/api/vendors", {
    data: { name, category: "logistics", contact_email: "ops@acmefreight.example" },
  });

  expect(response.status()).toBe(201);
});
