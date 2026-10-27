import { expect, test } from "../../fixtures";

test("profile shows the member role and tenant", { tag: "@AUTH-04" }, async ({ apiAs }) => {
  const member = await apiAs("member");

  const response = await member.get("/api/me");

  expect(response.status()).toBe(200);
  const profile = await response.json();
  expect(profile.role).toBe("member");
  expect(profile.tenant.name).toBe("Northwind Supply");
});
