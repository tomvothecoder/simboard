const DEFAULT_BROWSE_PAGE_SIZE = 25;

export const DEPRECATED_BROWSE_PARAM_KEYS = ['referenceStatus'] as const;

type BrowseFilterValue = string | string[];

interface ApplyBrowseUrlStateOptions<TFilterKey extends string> {
  currentParams: URLSearchParams;
  filters: Record<TFilterKey, BrowseFilterValue>;
  filterKeys: readonly TFilterKey[];
  page: number;
  pageSize: number;
  serializeArrayFilter: (values: string[]) => string;
  viewMode: 'grid' | 'table';
}

interface ResetBrowseUrlStateOptions {
  currentParams: URLSearchParams;
  filterKeys: readonly string[];
}

export const hasDeprecatedBrowseSearchParams = (params: URLSearchParams) =>
  DEPRECATED_BROWSE_PARAM_KEYS.some((key) => params.has(key));

export const normalizeBrowseSearchParams = (currentParams: URLSearchParams) => {
  const next = new URLSearchParams(currentParams);

  DEPRECATED_BROWSE_PARAM_KEYS.forEach((key) => {
    next.delete(key);
  });

  return next;
};

export const applyBrowseUrlState = <TFilterKey extends string>({
  currentParams,
  filters,
  filterKeys,
  page,
  pageSize,
  serializeArrayFilter,
  viewMode,
}: ApplyBrowseUrlStateOptions<TFilterKey>) => {
  const next = normalizeBrowseSearchParams(currentParams);

  for (const key of filterKeys) {
    const value = filters[key];

    if (Array.isArray(value) && value.length > 0) {
      next.set(key, serializeArrayFilter(value));
    } else if (typeof value === 'string' && value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
  }

  if (viewMode === 'grid') {
    next.set('view', 'grid');
  } else {
    next.delete('view');
  }

  if (page > 1) {
    next.set('page', String(page));
  } else {
    next.delete('page');
  }

  if (pageSize !== DEFAULT_BROWSE_PAGE_SIZE) {
    next.set('pageSize', String(pageSize));
  } else {
    next.delete('pageSize');
  }

  return next;
};

export const resetBrowseUrlState = ({ currentParams, filterKeys }: ResetBrowseUrlStateOptions) => {
  const next = normalizeBrowseSearchParams(currentParams);

  filterKeys.forEach((key) => {
    next.delete(key);
  });

  next.delete('page');

  return next;
};
