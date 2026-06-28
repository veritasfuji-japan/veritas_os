# Reviewer Failure Reason Catalog v1

Generated deterministic local/offline reviewer documentation.

- catalog_version: `reviewer-failure-reason-catalog-v1`
- generated_at: `2026-01-01T00:00:00Z`
- total_reasons: `59`

| reason | category | severity | reviewer label | affected artifacts |
|---|---|---|---|---|
| artifact_manifest_artifact_name_invalid | artifact_manifest | error | Artifact manifest artifact name invalid | artifact_manifest, reviewer_evidence_bundle |
| artifact_manifest_file_hash_mismatch | artifact_manifest | error | Artifact manifest file hash mismatch | artifact_manifest, reviewer_evidence_bundle |
| artifact_manifest_file_size_mismatch | artifact_manifest | error | Artifact manifest file size mismatch | artifact_manifest, reviewer_evidence_bundle |
| artifact_manifest_hash_mismatch | artifact_manifest | error | Artifact manifest hash mismatch | artifact_manifest, reviewer_evidence_bundle |
| artifact_manifest_json_unparseable | artifact_manifest | error | Artifact manifest json unparseable | artifact_manifest, reviewer_evidence_bundle |
| artifact_manifest_missing | artifact_manifest | error | Artifact manifest missing | artifact_manifest, reviewer_evidence_bundle |
| artifact_manifest_required_file_missing | artifact_manifest | error | Artifact manifest required file missing | artifact_manifest, reviewer_evidence_bundle |
| authority_expired_or_missing | authority | error | Authority expired or missing | reviewer_packet, authority_summary |
| authority_invalid | authority | error | Authority invalid | reviewer_packet, authority_summary |
| authority_missing | authority | error | Authority missing | reviewer_packet, authority_summary |
| blocked_case_outcome_failure_reasons_missing | demo_generation | error | Blocked case outcome failure reasons missing | demo_fixture, validation_report |
| blocked_case_refusal_basis_missing | demo_generation | error | Blocked case refusal basis missing | demo_fixture, validation_report |
| case_expectations_failed | demo_generation | error | Case expectations failed | demo_fixture, validation_report |
| demo_mismatched_links_present | demo_generation | error | Demo mismatched links present | demo_fixture, validation_report |
| evidence_chain_lifecycle_snapshot_hash_mismatch | lifecycle_snapshot_continuity | error | Evidence chain lifecycle snapshot hash mismatch | reviewer_packet, verifier_lifecycle_summary, evidence_chain_manifest, outcome_receipt |
| evidence_chain_manifest_lifecycle_snapshot_hash_missing | lifecycle_snapshot_continuity | error | Evidence chain manifest lifecycle snapshot hash missing | reviewer_packet, verifier_lifecycle_summary, evidence_chain_manifest, outcome_receipt |
| evidence_chain_outcome_lifecycle_snapshot_hash_missing | lifecycle_snapshot_continuity | error | Evidence chain outcome lifecycle snapshot hash missing | reviewer_packet, verifier_lifecycle_summary, evidence_chain_manifest, outcome_receipt |
| evidence_chain_verification_missing | packet_integrity | error | Evidence chain verification missing | reviewer_packet, evidence_chain_manifest, outcome_receipt |
| generated_packet_mismatch | demo_generation | error | Generated packet mismatch | demo_fixture, validation_report |
| golden_fixture_json_unparseable | demo_generation | error | Golden fixture json unparseable | demo_fixture, validation_report |
| golden_fixture_missing | demo_generation | error | Golden fixture missing | demo_fixture, validation_report |
| human_approval_action_class_mismatch | human_approval | error | Human approval action class mismatch | reviewer_packet, human_approval_summary |
| human_approval_bind_context_hash_mismatch | human_approval | error | Human approval bind context hash mismatch | reviewer_packet, human_approval_summary |
| human_approval_expired | human_approval | warning | Human approval expired | reviewer_packet, human_approval_summary |
| human_approval_missing | human_approval | error | Human approval missing | reviewer_packet, human_approval_summary |
| human_approval_request_ref_mismatch | human_approval | error | Human approval request ref mismatch | reviewer_packet, human_approval_summary |
| human_approval_scope_not_granted | human_approval | warning | Human approval scope not granted | reviewer_packet, human_approval_summary |
| local_offline_boundary_missing | demo_generation | error | Local offline boundary missing | demo_fixture, validation_report |
| packet_hash_length_invalid | packet_integrity | error | Packet hash length invalid | reviewer_packet, evidence_chain_manifest, outcome_receipt |
| packet_hash_missing | packet_integrity | error | Packet hash missing | reviewer_packet, evidence_chain_manifest, outcome_receipt |
| packet_hash_recompute_mismatch | packet_integrity | error | Packet hash recompute mismatch | reviewer_packet, evidence_chain_manifest, outcome_receipt |
| required_case_fields_missing | schema | error | Required case fields missing | reviewer_packet_schema, validation_report |
| required_top_level_fields_missing | schema | error | Required top level fields missing | reviewer_packet_schema, validation_report |
| reviewer_evidence_bundle_output_dir_invalid | demo_generation | error | Reviewer evidence bundle output dir invalid | demo_fixture, validation_report |
| reviewer_failure_reason_taxonomy_unknown | taxonomy | critical | Reviewer failure reason taxonomy unknown | reviewer_packet, validation_report |
| reviewer_packet_committed_lifecycle_status_not_clean | verifier_lifecycle | warning | Reviewer packet committed lifecycle status not clean | reviewer_packet, verifier_lifecycle_summary |
| reviewer_packet_human_approval_proof_continuity_invalid | verifier_continuity | error | Reviewer packet human approval proof continuity invalid | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_manifest_lifecycle_snapshot_hash_mismatch | lifecycle_snapshot_continuity | error | Reviewer packet manifest lifecycle snapshot hash mismatch | reviewer_packet, verifier_lifecycle_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_outcome_lifecycle_snapshot_hash_mismatch | lifecycle_snapshot_continuity | error | Reviewer packet outcome lifecycle snapshot hash mismatch | reviewer_packet, verifier_lifecycle_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verification_proof_hash_mismatch | packet_integrity | error | Reviewer packet verification proof hash mismatch | reviewer_packet, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verified_at_mismatch | verifier_continuity | error | Reviewer packet verified at mismatch | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_expired_before_verification | verifier_continuity | critical | Reviewer packet verifier expired before verification | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_id_mismatch | verifier_continuity | error | Reviewer packet verifier id mismatch | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_id_missing | verifier_continuity | error | Reviewer packet verifier id missing | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_key_id_mismatch | verifier_continuity | error | Reviewer packet verifier key id mismatch | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_lifecycle_invalid | verifier_lifecycle | error | Reviewer packet verifier lifecycle invalid | reviewer_packet, verifier_lifecycle_summary |
| reviewer_packet_verifier_lifecycle_policy_hash_mismatch | verifier_lifecycle | error | Reviewer packet verifier lifecycle policy hash mismatch | reviewer_packet, verifier_lifecycle_summary |
| reviewer_packet_verifier_lifecycle_snapshot_hash_mismatch | lifecycle_snapshot_continuity | error | Reviewer packet verifier lifecycle snapshot hash mismatch | reviewer_packet, verifier_lifecycle_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_lifecycle_snapshot_hash_missing | lifecycle_snapshot_continuity | error | Reviewer packet verifier lifecycle snapshot hash missing | reviewer_packet, verifier_lifecycle_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_not_yet_valid | verifier_continuity | critical | Reviewer packet verifier not yet valid | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_policy_hash_mismatch | verifier_continuity | error | Reviewer packet verifier policy hash mismatch | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_policy_hash_missing | verifier_continuity | error | Reviewer packet verifier policy hash missing | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_policy_id_missing | verifier_continuity | error | Reviewer packet verifier policy id missing | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| reviewer_packet_verifier_revoked_before_verification | verifier_continuity | critical | Reviewer packet verifier revoked before verification | reviewer_packet, human_approval_summary, evidence_chain_manifest, outcome_receipt |
| schema_file_json_unparseable | schema | error | Schema file json unparseable | reviewer_packet_schema, validation_report |
| schema_file_missing | schema | error | Schema file missing | reviewer_packet_schema, validation_report |
| schema_json_unparseable | schema | error | Schema json unparseable | reviewer_packet_schema, validation_report |
| schema_validation_failed | schema | error | Schema validation failed | reviewer_packet_schema, validation_report |
| valid_case_chain_not_verified | packet_integrity | warning | Valid case chain not verified | reviewer_packet, evidence_chain_manifest, outcome_receipt |

Explanations and remediation hints are available in the generated JSON catalog.
