import { PASSWORD, USERS, expect, test } from "../../fixtures";

test("signing out clears the session cookie", { tag: "@AUTH-06" }, async ({ request }) => {
  await request.post("/api/auth/login", { data: { email: USERS.member, password: PASSWORD } });

  const response = await request.post("/api/auth/logout");

  expect(response.status()).toBe(204);
  const cookie = response.headersArray().find((h) => h.name.toLowerCase() === "set-cookie")?.value ?? "";
  expect(cookie).toMatch(/^session=/);
  expect(cookie.toLowerCase()).toMatch(/max-age=0|expires=thu, 01 jan 1970/);
  expect((await request.get("/api/me")).status()).toBe(401);
});
