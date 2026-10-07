# Pre-Filing Checklist

**For review with a registered patent attorney before any filing decision.**
Nothing in this document is legal advice, and nothing in it establishes
novelty, non-obviousness, or claim validity — those are determinations
only a qualified attorney can make, informed by a real prior-art search
this document cannot substitute for. Its job is narrower: make sure the
attorney walks in with the organisational facts (what's been disclosed,
when, and to whom) that affect filing deadlines, not with a legal opinion
masquerading as one.

See `docs/claims/claim_map.yaml` and the dossier it builds
(`backend/scripts/build_dossier.py` → `docs/claims/patent_dossier.md`) for
the engineering evidence — which functions exist, which tests pass, what
the configuration's integrity hash is. This checklist is about everything
a dossier of code and tests cannot capture.

## 1. Public disclosure log

**Why this matters first:** most jurisdictions start a filing clock the
moment an invention is disclosed publicly without an NDA. In the US, the
AIA gives a 12-month grace period from the inventor's OWN disclosure; most
other jurisdictions (including the EPO) have ABSOLUTE novelty — a single
public disclosure, even by the inventor, can destroy patentability
outright with no grace period. Get this list complete and dated before
asking anything else.

- [ ] Every public repository push, and since when it has been public
      (vs. private). If this repository or a fork was ever public, note
      the exact date it became public: `__________`
- [ ] Any blog post, conference talk, poster, demo video, or social media
      post describing the DASE scoring approach, the classifier, the
      closed loop, or any other claimed mechanism. For each: date, venue,
      exact content shown/said, audience (was it under NDA?).
- [ ] Any academic paper, preprint (arXiv, SSRN, etc.), or thesis
      describing this work, published or submitted. Submission to a
      journal/conference for peer review typically counts as disclosure
      even before acceptance — list submission dates, not just
      publication dates.
- [ ] Any pitch deck, grant application, or accelerator application
      shared outside the inventors' own organisation, and whether each
      recipient was under NDA.
- [ ] Any live demo to students, teachers, or a school — was it to a
      closed pilot group under a data-use agreement, or open/public?
- [ ] Open-source licence on this repository (if any) and the date it was
      applied — an open-source licence is itself a public disclosure of
      everything it covers as of that commit.

**Action:** if any item above occurred more than 12 months before a
planned US filing, or at all before a planned filing in an absolute-
novelty jurisdiction, flag it to the attorney explicitly — it may limit
which jurisdictions remain available or require filing sooner than
otherwise planned.

## 2. Inventorship and ownership

- [ ] List every person who contributed to the conception of each claimed
      mechanism (not just who wrote the code — inventorship is about
      conception of the idea, which can differ from authorship of the
      implementation).
- [ ] For each contributor: employment status at time of contribution
      (employee, contractor, student, volunteer), and whether an IP
      assignment agreement was in place at that time.
- [ ] If any AI coding assistant materially contributed to the
      implementation of a claimed mechanism, note which ones and for
      which files — inventorship doctrine around AI-assisted
      development is unsettled in several jurisdictions and the attorney
      should know where this applies.
- [ ] University, employer, or grant-funding affiliations for any
      contributor — these can carry pre-existing IP assignment
      obligations (e.g. Bayh-Dole for US federally funded research) that
      affect who can file.

## 3. Prior art — organisational summary, not a legal search

This is NOT a substitute for a professional prior-art search (which the
attorney will commission). It exists so the attorney starts from what the
team already knows, rather than from zero.

- [ ] List every existing product, paper, or patent the team is already
      aware of that does something similar to any claim in
      `claim_map.yaml` — even ones believed to be distinguishable. Note
      why each is believed distinguishable; let the attorney confirm or
      correct that belief rather than assuming it.
- [ ] Specifically for each claim (`C1`-`C6` in `claim_map.yaml`): is
      there a known competitor or open-source project doing something
      similar? (e.g., adaptive-learning platforms using multi-dimensional
      scoring, any existing closed-loop item-remediation system, any
      existing "hesitation index" or similar non-biometric engagement
      signal in ed-tech.)
- [ ] Response-time-effort / rapid-guessing detection (the basis of the
      classifier's timing signal, `C2`) is established psychometrics —
      expect this specific mechanism to have prior art; the differentiator
      the attorney should be pointed at is the personal-baseline
      comparison + face-presence combination + confidence/abstention
      model, not response-time analysis in general.

## 4. Claim-strategy notes per claim

For each claim in `claim_map.yaml`, note here anything the engineering
dossier cannot capture:

| Claim | Known similar prior art | Believed differentiator | §101/abstract-idea risk (US) | Notes |
|---|---|---|---|---|
| C1 — disability-conditioned composite | ___ | Anchored to the measured-parameter/renormalization/coverage pipeline, not the weighting math alone | Pure weighted-sum math is vulnerable to an abstract-idea objection; claims should recite the sensor→classification→adaptation pipeline, not the arithmetic | ___ |
| C2 — cause classification | ___ | Personal baseline + face-presence + confidence/abstention, not response-time analysis alone | ___ | ___ |
| C3 — closed-loop re-presentation | ___ | Confidence-gated, pre-generated-variant serving tied to a specific classification | ___ | ___ |
| C4 — hesitation index | ___ | Non-biometric, interaction-only; explicitly not an anxiety/clinical inference | ___ | ___ |
| C5 — verified math steps | ___ | Deterministic re-verification of generative output before display, not the generation itself | ___ | ___ |
| C6 — KNOW/EXPR split scoring | ___ | Deterministic verbatim-span verification of a generative judgment | ___ | ___ |

## 5. Jurisdictional strategy notes

- [ ] Target jurisdictions for filing (US provisional? PCT? Direct
      national filings?) and the deadline each implies given §1's dates.
- [ ] India: §3(k) excludes "a mathematical method... or algorithm" from
      patentability as such — the same abstract-idea risk as US §101, with
      different case law. If India is a target jurisdiction, the attorney
      should weigh in on claim drafting specifically for this.
- [ ] EPO: absolute novelty (see §1) and its own approach to
      computer-implemented inventions (technical character requirement).
- [ ] Any jurisdiction where the educational/accessibility domain carries
      specific examination practice worth knowing in advance.

## 6. Reduction to practice

- [ ] For every claim element in `claim_map.yaml`, the dossier
      (`patent_dossier.md`) already states whether it's a resolved
      (built-and-tested) element or listed under "NOT YET REDUCED TO
      PRACTICE." Confirm with the attorney whether every claim needs full
      reduction to practice before filing, or whether a provisional can
      cover a constructive reduction to practice (a sufficiently detailed
      description without working code) for any still-open element.
- [ ] None of the ablation study results (`scripts/run_ablation.py`),
      ablation tables, ablation tables in `PHASE_LEARNINGS.md`, or the
      ```DASE weights``` are validated against real learner data — they
      are synthetic-archetype differentiation evidence, not efficacy
      evidence. Flag this distinction explicitly; it affects how strongly
      any "improves outcomes for X population" claim can be worded.

## 7. Before the attorney meeting

- [ ] This checklist, filled in.
- [ ] `docs/claims/claim_map.yaml` and a freshly-generated
      `docs/claims/patent_dossier.md` (`python scripts/build_dossier.py`
      from `backend/`, run it right before the meeting so it reflects the
      current repository state, not a stale snapshot).
- [ ] `docs/ROADMAP.md` and `docs/PHASE_LEARNINGS.md` for the honest
      implementation/limitations record — an attorney drafting claims
      broader than what the dossier and these docs support is a risk the
      team should flag, not discover later.
- [ ] A list of every person from §2, with contact information, in case
      the attorney needs to follow up on inventorship directly.
