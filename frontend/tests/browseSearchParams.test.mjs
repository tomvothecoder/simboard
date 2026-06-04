import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyBrowseUrlState,
  hasDeprecatedBrowseSearchParams,
  normalizeBrowseSearchParams,
  resetBrowseUrlState,
} from '../src/features/browse/browseSearchParams.ts';

test('normalizeBrowseSearchParams removes deprecated referenceStatus on initialization', () => {
  const params = new URLSearchParams('referenceStatus=with-reference&status=complete');

  const next = normalizeBrowseSearchParams(params);

  assert.equal(next.has('referenceStatus'), false);
  assert.equal(next.get('status'), 'complete');
});

test('applyBrowseUrlState removes deprecated referenceStatus during filter sync', () => {
  const next = applyBrowseUrlState({
    currentParams: new URLSearchParams('referenceStatus=with-reference&view=grid&page=3'),
    filters: {
      status: ['failed'],
      createdBy: [],
    },
    filterKeys: ['status', 'createdBy'],
    page: 1,
    pageSize: 25,
    serializeArrayFilter: (values) => values.join(','),
    viewMode: 'table',
  });

  assert.equal(next.has('referenceStatus'), false);
  assert.equal(next.get('status'), 'failed');
  assert.equal(next.has('view'), false);
  assert.equal(next.has('page'), false);
});

test('resetBrowseUrlState removes deprecated referenceStatus during reset', () => {
  const initial = new URLSearchParams('referenceStatus=with-reference&status=complete&page=2');

  assert.equal(hasDeprecatedBrowseSearchParams(initial), true);

  const next = resetBrowseUrlState({
    currentParams: initial,
    filterKeys: ['status'],
  });

  assert.equal(next.has('referenceStatus'), false);
  assert.equal(next.has('status'), false);
  assert.equal(next.has('page'), false);
});
