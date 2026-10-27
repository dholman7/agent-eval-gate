import { expect, test, uniqueName } from "../../fixtures";
import { createVendor } from "./_support";

test("vendors from another tenant are invisible", { tag: "@VEN-07" }, async ({ apiAs }) => {
  const other = await createVendor(await apiAs("otherTenant"), uniqueName("Globex Only"));

  const response = await (await apiAs("member")).get(`/api/vendors/${other.id}`);

  expect(response.status()).toBe(404);
  expect((await response.json()).error.code).toBe("vendor_not_found");
});
