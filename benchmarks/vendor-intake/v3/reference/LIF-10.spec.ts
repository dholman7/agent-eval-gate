import { expect, test, uniqueName } from "../../fixtures";
import { createVendor } from "./_support";

test("a vendor cannot be renamed to another vendor's name, whatever the case", { tag: "@LIF-10" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const atlas = await createVendor(member, uniqueName("Atlas Freight"));
  const borealis = await createVendor(member, uniqueName("Borealis Freight"));

  const response = await member.patch(`/api/vendors/${borealis.id}`, { data: { name: atlas.name.toUpperCase() } });

  expect(response.status(), await response.text()).toBe(409);
  expect((await response.json()).error.code).toBe("vendor_name_taken");
  expect(((await (await member.get(`/api/vendors/${borealis.id}`)).json()) as { name: string }).name).toBe(borealis.name);
});
