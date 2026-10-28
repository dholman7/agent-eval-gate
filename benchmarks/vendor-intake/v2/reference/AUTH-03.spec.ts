import { PASSWORD, USERS, expect, test } from "../../fixtures";

test("unknown email is rejected exactly like a wrong password", { tag: "@AUTH-03" }, async ({ request }) => {
  const unknown = await request.post("/api/auth/login", { data: { email: "nobody@northwind.test", password: PASSWORD } });
  const wrong = await request.post("/api/auth/login", { data: { email: USERS.member, password: "wrong-password" } });

  expect(unknown.status()).toBe(401);
  expect((await unknown.json()).error.code).toBe("invalid_credentials");
  expect(unknown.status()).toBe(wrong.status());
  expect((await unknown.json()).error).toEqual((await wrong.json()).error);
});
