import { expect, test, uniqueName } from "../../fixtures";

for (const [field, value] of [["name", "A"], ["category", "furniture"], ["contact_email", "not-an-email"]] as const) {
  test(`invalid ${field} is rejected and named`, { tag: "@VEN-02" }, async ({ apiAs }) => {
    const member = await apiAs("member");
    const body: Record<string, string> = {
      name: uniqueName("Valid Name"),
      category: "logistics",
      contact_email: "ops@valid.example",
    };
    body[field] = value;

    const response = await member.post("/api/vendors", { data: body });

    expect(response.status()).toBe(422);
    const error = (await response.json()).error;
    expect(error.code).toBe("validation_error");
    expect(error.fields.map((f: { field: string }) => f.field)).toEqual([field]);
  });
}
