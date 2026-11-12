import { expect, test } from "../../fixtures";
import { PASSWORD } from "../../fixtures";

test("sign-in ignores the case of the email address", { tag: "@LIF-11" }, async ({ request }) => {
  const response = await request.post("/api/auth/login", { data: { email: "Member@Northwind.TEST", password: PASSWORD } });

  expect(response.status(), await response.text()).toBe(200);
  const me = await request.get("/api/me", { headers: { Authorization: `Bearer ${(await response.json()).access_token}` } });
  expect(me.status(), await me.text()).toBe(200);
  expect((await me.json()).email).toBe("member@northwind.test");
});
