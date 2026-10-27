import { expect, test } from "../../fixtures";

test("requests without a session are rejected with not_authenticated", { tag: "@AUTH-05" }, async ({ request }) => {
  const response = await request.get("/api/me");

  expect(response.status()).toBe(401);
  expect((await response.json()).error.code).toBe("not_authenticated");
});
