/// <reference types="node" />
/** Types for ingress.cjs: pure Node image ingress (Base64 or data URI -> sniffed bytes). */
export type ImageMime = "image/png" | "image/jpeg" | "image/webp";

/** 32 MiB, the default decode limit. */
export const MAX_BYTES: number;
/** The image type from magic bytes, or null. */
export function sniff(bytes: Buffer): ImageMime | null;
/** Strict Base64 / data URI decoding; the declared MIME (if any) must match the sniffed one. */
export function decode(text: string, maxBytes?: number): {mimeType: ImageMime; bytes: Buffer};
