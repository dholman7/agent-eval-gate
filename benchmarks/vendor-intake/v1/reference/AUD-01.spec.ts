import { expect, test } from "../../fixtures";
import { W9, createVendor, uploadAndExtract } from "./_support";

test("audit events are listed oldest first with actor and time", { tag: "@AUD-01" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const vendor = await createVendor(member);
  await uploadAndExtract(member, vendor.id, "w9", W9);

  const response = await member.get(`/api/vendors/${vendor.id}/audit`);

  expect(response.status()).toBe(200);
  const items = (await response.json()).items as { action: string; at: string; actor: { email: string } }[];
  expect(items.map((e) => e.action)).toEqual(["vendor.created", "document.uploaded", "document.extracted"]);
  for (const event of items) {
    expect(event.actor.email).toBe("member@northwind.test");
    expect(Date.parse(event.at)).not.toBeNaN();
  }
});
