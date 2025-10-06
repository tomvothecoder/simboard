1
export type ExternalLinkType =
  | "diagnosticLinks"
  | "paceLinks"
  | "docs"
  | "other";

/**
 * Represents a link to an external diagnostic, documentation, or related resource.
 */
export interface ExternalLinkIn {
  linkType: ExternalLinkType;
  url: string;
  label?: string | null;
}

export interface ExternalLinkOut extends ExternalLinkIn {
  id: string;
  createdAt: string;
  updatedAt: string;
}
