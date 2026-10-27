import { expect, test } from "../../fixtures";

test("members cannot see the review queue", { tag: "@REV-04" }, async ({ apiAs }) => {
  const response = await (await apiAs("member")).get("/api/review-queue");

  expect(response.status()).toBe(403);
  expect((await response.json()).error.code).toBe("forbidden");
});
