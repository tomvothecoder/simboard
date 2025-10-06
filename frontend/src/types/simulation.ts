import type { ArtifactIn, ArtifactOut } from "@/types/artifact";
import type { ExternalLinkIn, ExternalLinkOut } from "@/types/link";
import type { Machine } from "@/types/machine";


/**
 * Request payload for creating a new simulation.
 */
export interface SimulationCreate {
  // Required fields
  name: string;
  caseName: string;
  compset: string;
  compsetAlias: string;
  gridName: string;
  gridResolution: string;
  initializationType: string;
  simulationType: string;
  status: string;
  machineId: string; // UUID
  modelStartDate: string; // ISO datetime

  // Optional fields
  versionTag?: string | null;
  gitHash?: string | null;
  parentSimulationId?: string | null;
  campaignId?: string | null;
  experimentTypeId?: string | null;
  groupName?: string | null;
  simulationEndDate?: string | null;
  totalYears?: number | null;
  runStartDate?: string | null;
  runEndDate?: string | null;
  compiler?: string | null;
  notesMarkdown?: string | null;
  knownIssues?: string | null;
  branch?: string | null;
  externalRepoUrl?: string | null;
  uploadedBy?: string | null;
  uploadDate?: string | null;
  lastModified?: string | null;
  lastEditedBy?: string | null;
  lastEditedAt?: string | null;
  extra?: Record<string, unknown>;

  // Relationships
  artifacts?: ArtifactIn[] | null;
  links?: ExternalLinkIn[] | null;
}

/**
 * API response model for a simulation (from FastAPI / DB).
 */
export interface SimulationOut {
  // Required fields
  id: string;
  name: string;
  caseName: string;
  compset: string;
  compsetAlias: string;
  gridName: string;
  gridResolution: string;
  initializationType: string;
  simulationType: string;
  status: string;
  machineId: string;
  modelStartDate: string;

  // Optional fields
  versionTag?: string | null;
  gitHash?: string | null;
  parentSimulationId?: string | null;
  campaignId?: string | null;
  experimentTypeId?: string | null;
  groupName?: string | null;
  simulationEndDate?: string | null;
  totalYears?: number | null;
  runStartDate?: string | null;
  runEndDate?: string | null;
  compiler?: string | null;
  notesMarkdown?: string | null;
  knownIssues?: string | null;
  branch?: string | null;
  externalRepoUrl?: string | null;
  uploadedBy?: string | null;
  uploadDate?: string | null;
  lastModified?: string | null;
  lastEditedBy?: string | null;
  lastEditedAt?: string | null;
  extra?: Record<string, unknown>;

  // Server-managed fields
  createdAt: string;
  updatedAt: string;

  // Relationships
  artifacts: ArtifactOut[];
  links: ExternalLinkOut[];
}

/**
 * Domain-friendly enriched simulation.
 * Adds a joined machine record for frontend convenience.
 */
export type Simulation = SimulationOut & {
  machine: Machine | null;
};
