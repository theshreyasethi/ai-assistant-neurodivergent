# Patent Claim-Support Dossier

**Generated automatically by `backend/scripts/build_dossier.py`. This is evidence
tooling, not legal advice** — every citation below is verified against the actual
repository state at build time, but novelty, validity and claim scope are
determinations for a registered patent attorney. See `docs/PRE_FILING_CHECKLIST.md`.

Config integrity (`backend/data/dase_profiles.json`): `sha256:3108d613ab88829712fcf7ddb17d4462b3c27c69f0e131a341e4cb2fc36e9aaa`

## C1

A method of scoring a learner's performance by computing a plurality of behavioral/interaction-derived parameters, applying a weighting profile selected according to a declared or inferred disability classification, excluding from the weighted composite any parameter for which a more severe form of the classified condition would mechanically depress the parameter independent of learning outcome, renormalizing the remaining weights over the parameters actually measurable for the given session, and reporting a coverage value indicating what fraction of the profile's intended weight was measured.

| Element | Code | Test | Status |
|---|---|---|---|
| C1.a | `backend/services/dase_engine.py::profile_weights` | `backend/tests/test_dase_formulas.py::test_composite_invariants` | resolved |
| C1.b | `backend/services/dase_engine.py::diagnostic_only` | `backend/tests/test_dase_formulas.py::test_override_weights_replace_profile_defaults_but_keep_diagnostic_rule` | resolved |
| C1.c | `backend/services/dase_engine.py::compute_dase` | `backend/tests/test_dase_formulas.py::test_composite_is_monotonic_in_accuracy_when_all_else_equal` | resolved |
| C1.d | `backend/routers/overrides.py::set_weight_override` | `backend/tests/test_overrides_and_scoring.py::test_mapped_teacher_can_set_an_override_and_it_changes_the_next_score` | resolved |

## C2

A method of classifying the probable cause of an incorrect learner response by comparing the response's latency against that specific learner's own historical response-time baseline (never a cohort or population baseline) in combination with a face-presence signal, producing a labelled classification with an associated confidence value and, where two causes are indistinguishable on the available signals, abstaining to a default label while recording the alternative causes rather than selecting one by default.

| Element | Code | Test | Status |
|---|---|---|---|
| C2.a | `backend/services/dase_engine.py::rolling_median` | `backend/tests/test_classifier.py::test_thin_baseline_caps_confidence_even_on_a_clear_processing_delay` | resolved |
| C2.b | `backend/services/dase_engine.py::classify_error` | `backend/tests/test_classifier.py::test_classifier_abstains_without_focus_data` | resolved |
| C2.c | `backend/services/dase_engine.py::classify_error` | `backend/tests/test_classifier.py::test_classifier_abstains_with_too_few_focus_samples` | resolved |
| C2.d | `backend/routers/telemetry.py::_reclassify_if_stale` | `backend/tests/test_telemetry_reclassification.py::test_stale_classifier_version_is_recomputed` | resolved |

## C3

A method of serving a pre-generated, profile-constrained simpler variant of a learning item immediately upon classifying an incorrect response as a comprehension barrier at or above a confidence threshold, tracking the re-presented attempt as a distinct event correlated to the original item rather than overwriting the original record.

| Element | Code | Test | Status |
|---|---|---|---|
| C3.a | `backend/services/dase_engine.py::should_represent` | `backend/tests/test_classifier.py::test_should_represent_true_only_for_confident_comprehension_barrier` | resolved |
| C3.b | `frontend/src/pages/QuizPage.tsx::handleSubmit` | `backend/tests/test_contract.py::test_frontend_shaped_event_reaches_the_engine_and_is_classified` | resolved |

## C4

A method of computing a non-clinical, interaction-only resilience signal from a combination of: response latency relative to the learner's own baseline, frequency of response revision, frequency of input-focus loss, and a mean sentiment score derived from a conversational support interface, where the signal's constituent weights are renormalized over whichever inputs are available for a given session rather than requiring all four.

| Element | Code | Test | Status |
|---|---|---|---|
| C4.a | `backend/services/hesitation.py::hesitation_index` | `backend/tests/test_phase4_services.py::test_hesitation_index_renormalizes_over_available_signals` | resolved |
| C4.b | `backend/services/dase_engine.py::_resil` | `backend/tests/test_dase_formulas.py::test_resil_present_from_answer_changes_and_latency_alone` | resolved |

## C5

A method of presenting a machine-generated, multi-step numeric solution to a learner in which each proposed step is independently re-evaluated by a deterministic, restricted expression evaluator before being displayed, such that a step whose claimed result does not match independent re-evaluation is discarded rather than shown, combined with a deterministic (non-generative) typing of the conceptual or procedural cause of an incorrect numeric response.

| Element | Code | Test | Status |
|---|---|---|---|
| C5.a | `backend/services/math_steps.py::safe_eval` | `backend/tests/test_phase4_services.py::test_safe_eval_rejects_function_calls` | resolved |
| C5.b | `backend/services/math_steps.py::verify_steps` | `backend/tests/test_phase4_services.py::test_verify_steps_drops_a_step_whose_result_does_not_check_out` | resolved |
| C5.c | `backend/services/math_steps.py::classify_math_error` | `backend/tests/test_phase4_services.py::test_classify_math_error_truth_table` | resolved |

## C6

A method of scoring a learner's free-form written response along two independent axes — concept coverage and written-expression quality — in which concept coverage is computed deterministically from a machine-identified evidentiary span that is independently verified to appear verbatim in the learner's own response (a claimed match that fails this verification is rejected regardless of the machine's own assertion), and the written-expression axis is excluded from any composite score for a condition whose more severe form would mechanically depress it.

| Element | Code | Test | Status |
|---|---|---|---|
| C6.a | `backend/services/writing_score.py::score_know` | `backend/tests/test_phase4_services.py::test_score_know_rejects_a_claimed_quote_that_is_not_actually_in_the_answer` | resolved |
| C6.b | `backend/services/writing_score.py::score_expr` | `backend/tests/test_phase4_services.py::test_score_expr_computes_weighted_rubric` | resolved |
