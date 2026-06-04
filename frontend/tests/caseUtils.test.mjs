import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getAnchorChangeCount,
  getAnchorStatusLabel,
  getGroupChangeSummaryLabel,
} from '../src/features/simulations/caseUtils.ts';

test('getAnchorChangeCount hides stale changeCount for hashless simulations', () => {
  const simulation = {
    caseHash: null,
    isAnchorRun: false,
    anchorSimulationId: 'anchor-1',
    changeCount: 4,
  };

  assert.equal(getAnchorChangeCount(simulation), null);
  assert.equal(getAnchorStatusLabel(simulation), 'No comparison anchor');
});

test('getAnchorChangeCount preserves changeCount for anchored non-hashless simulations', () => {
  const simulation = {
    caseHash: 'case-hash',
    isAnchorRun: false,
    anchorSimulationId: 'anchor-1',
    changeCount: 2,
  };

  assert.equal(getAnchorChangeCount(simulation), 2);
});

test('getGroupChangeSummaryLabel uses non-comparison copy for hashless fallback groups', () => {
  const label = getGroupChangeSummaryLabel([
    {
      caseHash: null,
      isAnchorRun: false,
      anchorSimulationId: 'anchor-1',
      changeCount: 7,
    },
    {
      caseHash: null,
      isAnchorRun: false,
      anchorSimulationId: 'anchor-2',
      changeCount: 3,
    },
  ]);

  assert.equal(label, 'No comparison anchor');
});
