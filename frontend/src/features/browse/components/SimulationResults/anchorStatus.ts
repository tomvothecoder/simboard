import type { SimulationOut } from '@/types';

export const getBrowseAnchorStatusLabel = (simulation: SimulationOut) => {
  if (simulation.anchorSimulationId == null) {
    return 'No comparison anchor';
  }

  if (simulation.isAnchorRun) {
    return 'Anchor run';
  }

  if (simulation.caseHash == null) {
    return 'No comparison anchor';
  }

  if (simulation.changeCount > 0) {
    return `${simulation.changeCount} changes from anchor run`;
  }

  return 'No recorded changes from anchor run';
};
