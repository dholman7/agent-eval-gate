import { USERS, expect, test } from "../../fixtures";

test("wrong password is rejected with invalid_credentials", { tag: "@AUTH-02" }, async ({ request }) => {
  const response = await request.post("/api/auth/login", { data: { email: USERS.member, password: "wrong-password" } });

  expect(response.status()).toBe(401);
  expect((await response.json()).error.code).toBe("invalid_credentials");
});
