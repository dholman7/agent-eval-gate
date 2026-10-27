// Shared helpers for the reference tests. Installed next to each reference spec while scoring.
import { expect, type APIRequestContext, type APIResponse } from "@playwright/test";

import { uniqueName } from "../../fixtures";

export const W9 = "Legal Name: Acme Freight LLC\nTax ID: 12-3456789\nBusiness Type: LLC\n";
export const CONTRACT = "Counterparty: Acme Freight LLC\nEffective Date: 2026-01-01\nExpiry Date: 2030-12-31\n";

export function insurance(expiry = "2030-03-31"): string {
  return `Insurer: Harbor Mutual\nPolicy Number: HM-55-1290\nCoverage Amount: $2,000,000\nExpiry Date: ${expiry}\n`;
}

/** The server compares against its UTC date, so tests do too. */
export function isoDaysFromToday(days: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export interface Vendor {
  id: string;
  name: string;
  status: string;
  flags: string[];
}

export async function createVendor(api: APIRequestContext, name = uniqueName("Reference Vendor")): Promise<Vendor> {
  const response = await api.post("/api/vendors", {
    data: { name, category: "logistics", contact_email: "ops@reference.example" },
  });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as Vendor;
}

export function upload(
  api: APIRequestContext,
  vendorId: string,
  kind: string,
  content: string | Buffer,
  filename = "document.txt",
  mimeType = "text/plain",
): Promise<APIResponse> {
  return api.post(`/api/vendors/${vendorId}/documents`, {
    multipart: { kind, file: { name: filename, mimeType, buffer: Buffer.from(content) } },
  });
}

export async function waitForExtraction(api: APIRequestContext, documentId: string): Promise<void> {
  await expect
    .poll(async () => ((await (await api.get(`/api/documents/${documentId}`)).json()) as { status: string }).status)
    .toBe("extracted");
}

export async function uploadAndExtract(api: APIRequestContext, vendorId: string, kind: string, content: string) {
  const response = await upload(api, vendorId, kind, content);
  expect(response.status(), await response.text()).toBe(201);
  const document = (await response.json()) as { id: string };
  await waitForExtraction(api, document.id);
  return document;
}

/** Draft vendor with all three documents uploaded and extracted. */
export async function readyVendor(api: APIRequestContext, options: { insurance?: string; name?: string } = {}) {
  const vendor = await createVendor(api, options.name);
  await uploadAndExtract(api, vendor.id, "w9", W9);
  await uploadAndExtract(api, vendor.id, "insurance_certificate", options.insurance ?? insurance());
  await uploadAndExtract(api, vendor.id, "contract", CONTRACT);
  return vendor;
}

export async function inReviewVendor(api: APIRequestContext, options: { insurance?: string; name?: string } = {}) {
  const vendor = await readyVendor(api, options);
  const response = await api.post(`/api/vendors/${vendor.id}/submit`);
  expect(response.status(), await response.text()).toBe(200);
  return vendor;
}

export interface Extraction {
  id: string;
  kind: string;
  status: string;
  fields: Record<string, { value: string | null; confidence: number }>;
}

export async function extractions(api: APIRequestContext, vendorId: string): Promise<Record<string, Extraction>> {
  const documents = (await (await api.get(`/api/vendors/${vendorId}/documents`)).json()) as { id: string; kind: string }[];
  const entries = await Promise.all(
    documents.map(async (d) => [d.kind, await (await api.get(`/api/documents/${d.id}/extraction`)).json()] as const),
  );
  return Object.fromEntries(entries) as Record<string, Extraction>;
}

export async function auditActions(api: APIRequestContext, vendorId: string): Promise<string[]> {
  const trail = (await (await api.get(`/api/vendors/${vendorId}/audit`)).json()) as { items: { action: string }[] };
  return trail.items.map((e) => e.action);
}

export async function vendorStatus(api: APIRequestContext, vendorId: string): Promise<string> {
  return ((await (await api.get(`/api/vendors/${vendorId}`)).json()) as Vendor).status;
}
