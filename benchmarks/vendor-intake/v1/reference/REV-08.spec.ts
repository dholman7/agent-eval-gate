import { expect, test } from "../../fixtures";
import { createVendor, insurance, isoDaysFromToday, uploadAndExtract } from "./_support";

for (const [days, flagged] of [[0, true], [30, true], [31, false]] as const) {
  test(`insurance expiring in ${days} days is ${flagged ? "" : "not "}flagged`, { tag: "@REV-08" }, async ({ apiAs }) => {
    const member = await apiAs("member");
    const vendor = await createVendor(member);
    await uploadAndExtract(member, vendor.id, "insurance_certificate", insurance(isoDaysFromToday(days)));

    const flags = (await (await member.get(`/api/vendors/${vendor.id}`)).json()).flags as string[];

    expect(flags.includes("insurance_expiring_soon")).toBe(flagged);
  });
}
