# ClaimCheck — Threat Model & Scope

This document states, deliberately and up front, what ClaimCheck is for, what it
will and will not do, and the boundaries that keep a tool built on a famous
*offensive* technique squarely on the *defensive* side.

## 1. Purpose

ClaimCheck is a **defensive exposure-assessment tool**. Its deliverable is a
**report** that tells defenders which of *their own* internal package names an
attacker could claim on the public PyPI/npm registries (the dependency-confusion
/ substitution attack), so they can pre-empt it.

It inverts the attacker's reconnaissance — *discover the internal names, test
which are claimable* — and runs that reconnaissance **for the defender first**,
turning it into a pre-emptive audit.

## 2. The attack, briefly

Internal packages (`acme-auth`, `@acme/billing`) live on a private registry. Many
package managers, asked to install such a name, will pull it from the **public**
registry if a higher version exists there. An attacker who learns the name
publishes it publicly with a huge version number; the victim's build silently
pulls the attacker's code, which can run at install time. The exposure is a
**namespace fact** (does the public name exist, and would your config fall back
to it?) that no code scanner or CVE database checks — ClaimCheck checks exactly
that.

## 3. Strictly read-only against registries

- ClaimCheck **only reads** public registry data (existence, owner, publish
  date) via HTTP **GET**.
- It **never** publishes, registers, reserves, or squats a package name — not
  even defensively. Registering a name is a deliberate action left entirely to
  the human operator.
- The repository **ships no publishing capability**. This invariant is enforced
  by an automated test (`tests/test_readonly.py`) that fails the build if any
  mutating HTTP verb or publishing tool appears in the source.

## 4. Assess your own names only

- ClaimCheck is for checking the internal names of an organization **you own or
  are authorized to assess**.
- It is **not** a mass-scanner for discovering *other* companies' claimable names
  or squatting opportunities. The synthetic data and docs make this explicit, and
  all bundled examples use fictional, operator-controlled names (`acme-*`,
  `@acme/*`, `acmecorp-*`). "Already-squatted" test cases use the fictional owner
  `mallory` and never reference a real organization's real internal package
  names.
- Pointing the tool at a third party to find names they have not claimed is
  outside its intended use.

## 5. Point-in-time caveat (honesty)

- `SAFE` / `PROTECTED` reflect the registry and configuration state **at scan
  time**. Registries and install configs change, so **re-scan in CI**.
- `CLAIMABLE` is authoritative about *current* exposure, but the absence of
  exposure today is not a permanent guarantee.
- A `PROTECTED` verdict depends on configuration (reserved scope / pinned index);
  a later config change can silently re-open the exposure. This is exactly why
  ClaimCheck is designed to run as a recurring CI gate, not a one-off.

## 6. Known limitations

- Without an operator allowlist/prefix, an internal name that has **already been
  squatted** can look like a normal public dependency (a false negative). Supply
  an allowlist (`--config`) for best accuracy.
- A public package that merely **collides with an internal prefix** may be
  over-flagged (`TAKEN-NOT-YOURS`) when it is in fact a legitimate external
  dependency (a false positive). Tune `owned_public_names` / prefixes to resolve.
- The curated well-known lists are small and high-signal, not a full registry
  mirror; the live probe is authoritative about existence.

## 7. Responsible use

- Run ClaimCheck on **your own** dependency surface.
- The remediation it recommends (defensively register, reserve the scope, pin the
  index, investigate a squat) is performed **by you, deliberately** — never by
  the tool.
- Treat the output as sensitive: a `CLAIMABLE` list is a map of your exposure.
  Share it only with those authorized to act on it.
