import { expect, test } from "../../fixtures";
import {
  CONTRACT, W9, createVendor, insurance, queueItem, uploadAndExtract,
} from "./_support";

test("a re-uploaded document is the one that gets reviewed", { tag: "@LIF-01" }, async ({ apiAs }) => {
  const member = await apiAs("member");
  const reviewer = await apiAs("reviewer");
  const vendor = await createVendor(member);
  await uploadAndExtract(member, vendor.id, "insurance_certificate", insurance());
  await uploadAndExtract(member, vendor.id, "contract", CONTRACT);
  const first = await uploadAndExtract(member, vendor.id, "w9", W9.replace("Acme Freight LLC", "First Name LLC"));
  const second = await uploadAndExtract(member, vendor.id, "w9", W9.replace("Acme Freight LLC", "Second Name LLC"));

  const submitted = await member.post(`/api/vendors/${vendor.id}/submit`);
  expect(submitted.status(), await submitted.text()).toBe(200);
  const item = await queueItem(reviewer, vendor.id);

  const w9 = item?.extractions.find((e) => e.kind === "w9");
  expect(w9?.fields.legal_name.value).toBe("Second Name LLC");
  const documents = (await (await member.get(`/api/vendors/${vendor.id}/documents`)).json()) as { id: string; kind: string }[];
  expect(documents.filter((d) => d.kind === "w9").map((d) => d.id)).toEqual([first.id, second.id]);
});
