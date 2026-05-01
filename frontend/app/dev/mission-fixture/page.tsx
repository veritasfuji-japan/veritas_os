import { MissionPage } from "../../../components/mission-page";
import { I18nProvider } from "../../../components/i18n-provider";
import { resolveMissionGovernanceSnapshot } from "../../../components/mission-governance-adapter";
import fixturePayload from "../../../fixtures/governance_observation_live_snapshot.json";

export default function DevMissionFixturePage(): JSX.Element {
  const governanceLayerSnapshot = resolveMissionGovernanceSnapshot(fixturePayload);

  return (
    <I18nProvider>
      <div className="space-y-6" data-testid="dev-mission-fixture-page">
        <section className="rounded-md border border-warning/60 bg-warning/5 p-4" aria-label="dev-only-fixture-banner">
          <p className="font-semibold">DEV-ONLY FIXTURE</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            <li>Runtime behavior is unchanged</li>
            <li>Production still fails closed</li>
            <li>Observe Mode runtime is not enabled</li>
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">Fixture source: frontend/fixtures/governance_observation_live_snapshot.json (copied from fixtures/governance_observation_live_snapshot.json)</p>
        </section>

        <MissionPage
          title="Dev-only Mission Control Fixture Viewer"
          subtitle="Static fixture rendering for governance_observation contract verification"
          chips={["DEV-ONLY FIXTURE", "STATIC SNAPSHOT", "READ-ONLY"]}
          governanceLayerSnapshot={governanceLayerSnapshot}
        />
      </div>
    </I18nProvider>
  );
}
