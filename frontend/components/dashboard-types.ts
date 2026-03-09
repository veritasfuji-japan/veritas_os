export type HealthBand = "healthy" | "degraded" | "critical";

export interface CriticalRailMetric {
  key: string;
  label: string;
  severity: HealthBand;
  currentValue: string;
  baselineDelta: string;
  owner: string;
  lastUpdated: string;
  openIncidents: number;
  href: string;
}

export interface OpsPriorityItem {
  key: string;
  titleJa: string;
  titleEn: string;
  owner: string;
  whyNowJa: string;
  whyNowEn: string;
  impactWindowJa: string;
  impactWindowEn: string;
  ctaJa: string;
  ctaEn: string;
  href: string;
}

export interface GlobalHealthSummaryModel {
  band: HealthBand;
  todayChanges: string[];
  incidents24h: string;
  policyDrift: string;
  trustDegradation: string;
  decisionAnomalies: string;
}
