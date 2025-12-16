import type { SimulationOut } from '@/types/index';

import api from './api';

export const fetchAISimAnalysis = async (simulations: SimulationOut[]): Promise<string> => {
  const response = await api.post(`/analyze-simulations`, {
    simulations,
  });
  return response.data.summary;
};
