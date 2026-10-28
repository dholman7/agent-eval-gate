import { PASSWORD, USERS, expect, test } from "../../fixtures";

test("successful sign-in returns a token and an HttpOnly session cookie", { tag: "@AUTH-01" }, async ({ request }) => {
  const response = await request.post("/api/auth/login", { data: { email: USERS.member, password: PASSWORD } });

  expect(response.status()).toBe(200);
  expect((await response.json()).access_token).toBeTruthy();
  const cookie = response.headersArray().find((h) => h.name.toLowerCase() === "set-cookie")?.value ?? "";
  expect(cookie).toMatch(/^session=/);
  expect(cookie.toLowerCase()).toContain("httponly");
});
