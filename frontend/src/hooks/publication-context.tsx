"use client";
import { createContext, useContext } from "react";
import type { ReadMetadata } from "@/services/api/http";
export const PublicationContext = createContext<ReadMetadata | undefined>(
  undefined,
);
export const usePublicationMetadata = () => useContext(PublicationContext);
// Only the explicit loopback preview may retain an unbound demo workspace.
export const PreviewDemoContext = createContext(false);
export const usePreviewDemo = () => useContext(PreviewDemoContext);
