# Feature Specification: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`  
**Created**: [DATE]  
**Status**: Draft  
**Input**: User description: "$ARGUMENTS"

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - [Brief Title] (Priority: P1)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently - e.g., "Can be fully tested by [specific action] and delivers [specific value]"]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 2 - [Brief Title] (Priority: P2)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 3 - [Brief Title] (Priority: P3)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- What happens when a sender has less mass than the nominal outflow request?
- What happens when a receiver is capacity-constrained or shared across flows?
- What happens when `dt` changes or a quantity crosses a multirate boundary?
- How does the system reject invalid states, out-of-range inputs, or same-tick
  positive feedback loops?

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: System MUST [specific capability, e.g., "allow users to create accounts"]
- **FR-002**: System MUST [specific capability, e.g., "validate email addresses"]  
- **FR-003**: Users MUST be able to [key interaction, e.g., "reset their password"]
- **FR-004**: System MUST [data requirement, e.g., "persist user preferences"]
- **FR-005**: System MUST [behavior, e.g., "log all security events"]

*Example of marking unclear requirements:*

- **FR-006**: System MUST authenticate users via [NEEDS CLARIFICATION: auth method not specified - email/password, SSO, OAuth?]
- **FR-007**: System MUST retain user data for [NEEDS CLARIFICATION: retention period not specified]

### Contract & Interface Requirements *(mandatory for new or changed public APIs)*

- **CR-001**: Each new or changed public function MUST specify inputs, outputs,
  units, admissible ranges, invariants preserved, and failure conditions.
- **CR-002**: Invalid states and out-of-contract inputs MUST state whether they
  raise, reject, or return structured failure.
- **CR-003**: Contract ownership MUST be explicit: identify the authoritative
  code location or contract document for each public interface change.

### Dynamics, Time, and Conservation Requirements *(mandatory for simulation logic)*

- **DR-001**: Each evolving quantity MUST be labeled as a stock, per-tick
  increment, or per-unit-time rate.
- **DR-002**: Each `dt` conversion MUST be explicit, documented, and testable.
- **DR-003**: Traffic transfer rules MUST specify sender limits, receiver
  limits, shared budgets, and conservation expectations.
- **DR-004**: Same-tick positive feedback closures MUST be ruled out or modeled
  explicitly with justification and stability tests.

### Determinism & Auditability Requirements *(mandatory for stateful or stochastic features)*

- **DA-001**: Equivalent inputs, seeds, and journals MUST reproduce equivalent
  outcomes.
- **DA-002**: Hidden state mutation and cross-run state leakage MUST be ruled
  out.
- **DA-003**: The feature MUST identify how affected updates are inspected:
  replay artifact, targeted log, benchmark output, or regression test.

### Key Entities *(include if feature involves data)*

- **[Entity 1]**: [What it represents, key attributes without implementation]
- **[Entity 2]**: [What it represents, relationships to other entities]

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: [Measurable metric, e.g., "Users can complete account creation in under 2 minutes"]
- **SC-002**: [Measurable metric, e.g., "System handles 1000 concurrent users without degradation"]
- **SC-003**: [User satisfaction metric, e.g., "90% of users successfully complete primary task on first attempt"]
- **SC-004**: [Business metric, e.g., "Reduce support tickets related to [X] by 50%"]

## Validation & Regression Plan *(mandatory)*

- **VR-001**: List the targeted regression tests that cover repaired failure
  modes or changed invariants.
- **VR-002**: List the baseline reproduction scenario or toy benchmark that
  proves the feature still matches expected behavior.
- **VR-003**: List the edge and adversarial cases that must pass before broad
  suite runs.
- **VR-004**: State what deterministic replay evidence is required, or explain
  why replay is unaffected.

## Assumptions

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right assumptions based on reasonable defaults
  chosen when the feature description did not specify certain details.
-->

- [Assumption about target users, e.g., "Users have stable internet connectivity"]
- [Assumption about scope boundaries, e.g., "Mobile support is out of scope for v1"]
- [Assumption about data/environment, e.g., "Existing authentication system will be reused"]
- [Dependency on existing system/service, e.g., "Requires access to the existing user profile API"]

## Remaining Risks *(mandatory)*

- [Risk that remains after implementation, e.g., "Benchmark coverage is still
  limited to corridor-scale scenarios"]
- [Deferred follow-up, fallback path, or degraded guarantee that reviewers
  should understand before sign-off]
