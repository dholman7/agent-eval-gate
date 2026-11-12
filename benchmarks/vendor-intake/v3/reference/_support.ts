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

/** The audit actions of a vendor this test created, checked to be its own trail: one creation, first. */
export async function auditActions(api: APIRequestContext, vendorId: string): Promise<string[]> {
  const trail = (await (await api.get(`/api/vendors/${vendorId}/audit`)).json()) as { items: { action: string }[] };
  const actions = trail.items.map((e) => e.action);
  // Events carry no vendor id, so a trail mixing in other vendors' events shows as extra creations.
  expect(actions.filter((a) => a === "vendor.created"), `trail: ${actions.join(", ")}`).toHaveLength(1);
  expect(actions[0]).toBe("vendor.created");
  return actions;
}

export async function vendorStatus(api: APIRequestContext, vendorId: string): Promise<string> {
  return ((await (await api.get(`/api/vendors/${vendorId}`)).json()) as Vendor).status;
}

// --- v3: lifecycle tasks ---------------------------------------------------------------------

export function decide(
  api: APIRequestContext,
  extractionId: string,
  decision: "approve" | "reject",
  note?: string,
): Promise<APIResponse> {
  return api.post(`/api/extractions/${extractionId}/decision`, { data: note ? { decision, note } : { decision } });
}

export async function decided(api: APIRequestContext, extractionId: string, decision: "approve" | "reject", note?: string) {
  const response = await decide(api, extractionId, decision, note);
  expect(response.status(), await response.text()).toBe(200);
}

export interface QueueItem {
  vendor_id: string;
  extractions: Extraction[];
}

export async function queueItem(api: APIRequestContext, vendorId: string): Promise<QueueItem | undefined> {
  const response = await api.get("/api/review-queue");
  expect(response.status(), await response.text()).toBe(200);
  return ((await response.json()) as QueueItem[]).find((i) => i.vendor_id === vendorId);
}

export interface VendorPage {
  items: Vendor[];
  total: number;
}

export async function listVendors(api: APIRequestContext, query: Record<string, string | number>): Promise<VendorPage> {
  const response = await api.get("/api/vendors", { params: query });
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()) as VendorPage;
}

/** A vendor whose `rejected` extraction a reviewer rejected after approving the `approved` ones. */
export async function sentBackVendor(
  member: APIRequestContext,
  reviewer: APIRequestContext,
  rejected: string,
  approved: string[] = [],
): Promise<Vendor> {
  const vendor = await inReviewVendor(member);
  const all = await extractions(member, vendor.id);
  for (const kind of approved) await decided(reviewer, all[kind].id, "approve");
  await decided(reviewer, all[rejected].id, "reject", "Please send a corrected copy");
  return vendor;
}
