import { expect, test, uniqueName } from "../../fixtures";
import { sentBackVendor } from "./_support";

test("a vendor that was sent back can be edited again", { tag: "@LIF-09" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await sentBackVendor(member, await apiAs("reviewer"), "contract");
  const name = uniqueName("Renamed Vendor");

  const response = await member.patch(`/api/vendors/${vendor.id}`, { data: { name } });

  expect(response.status(), await response.text()).toBe(200);
  expect(((await (await member.get(`/api/vendors/${vendor.id}`)).json()) as { name: string }).name).toBe(name);
});
