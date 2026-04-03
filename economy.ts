import apiClient from './client';

export interface EconomyMetric {
  key: string;
  label: string;
  unit: string;
  raw_value: number | null;
  display_value: string;
  meta: string;
  source_label: string | null;
}

export interface EconomySection {
  key: string;
  label: string;
  badge: string;
  as_of_label: string;
  metrics: EconomyMetric[];
}

export interface EconomySnapshot {
  source_label: string;
  workbook_label: string;
  workbook_period_label: string;
  as_of_label: string;
  extracted_at: string;
  sections: Record<string, EconomySection>;
}

export async function getEconomySnapshot(): Promise<EconomySnapshot> {
  const response = await apiClient.get('/economy/nrb-snapshot');
  return response.data;
}

