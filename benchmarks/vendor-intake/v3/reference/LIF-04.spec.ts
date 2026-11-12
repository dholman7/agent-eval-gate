import { expect, test } from "../../fixtures";
import { sentBackVendor } from "./_support";

test("resubmitting without replacing the rejected document is refused", { tag: "@LIF-04" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await sentBackVendor(member, await apiAs("reviewer"), "w9");

  const response = await member.post(`/api/vendors/${vendor.id}/submit`);

  expect(response.status(), await response.text()).toBe(409);
  const error = (await response.json()).error;
  expect(error.code).toBe("documents_incomplete");
  expect(error.missing_kinds).toEqual(["w9"]);
});
