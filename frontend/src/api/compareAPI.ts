import axios from 'axios';

import type { SimulationOut } from '@/types/index';

export const fetchAISimAnalysis = async (simulations: SimulationOut[]): Promise<string> => {
  const response = await axios.post(`/analyze-simulations`, {
    simulations,
  });
  return response.data.summary;
};
