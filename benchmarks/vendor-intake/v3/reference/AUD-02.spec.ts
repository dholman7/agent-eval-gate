import { expect, test, uniqueName } from "../../fixtures";
import { createVendor } from "./_support";

test("audit trails from another tenant are invisible", { tag: "@AUD-02" }, async ({ apiAs }) => {
  const other = await createVendor(await apiAs("otherTenant"), uniqueName("Globex Only"));

  const response = await (await apiAs("member")).get(`/api/vendors/${other.id}/audit`);

  expect(response.status()).toBe(404);
});
