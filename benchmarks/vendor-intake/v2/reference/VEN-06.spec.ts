import { expect, test } from "../../fixtures";

test("pagination limit above 100 is rejected", { tag: "@VEN-06" }, async ({ apiAs }) => {
  const member = await apiAs("member");

  const response = await member.get("/api/vendors", { params: { limit: 101 } });

  expect(response.status()).toBe(422);
});
