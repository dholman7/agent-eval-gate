import { expect, test } from "../../fixtures";
import { inReviewVendor, insurance } from "./_support";

test("the review queue lists the least confident vendor first", { tag: "@REV-03" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const confident = await inReviewVendor(member);
  const shaky = await inReviewVendor(member, { insurance: insurance("next spring") });

  const queue = (await (await (await apiAs("reviewer")).get("/api/review-queue")).json()) as {
    vendor_id: string;
    lowest_confidence: number;
  }[];

  const shakyIndex = queue.findIndex((i) => i.vendor_id === shaky.id);
  const confidentIndex = queue.findIndex((i) => i.vendor_id === confident.id);
  expect(shakyIndex).toBeGreaterThanOrEqual(0);
  expect(confidentIndex).toBeGreaterThan(shakyIndex);
  expect(queue[shakyIndex].lowest_confidence).toBeLessThan(queue[confidentIndex].lowest_confidence);
  const confidences = queue.map((i) => i.lowest_confidence);
  expect(confidences).toEqual([...confidences].sort((a, b) => a - b));
});
