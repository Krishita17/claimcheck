# ClaimCheck Exposure Report

- **Target:** `samples/acme`
- **Mode:** mock
- **Names analyzed:** 21

## Summary

| Verdict | Count |
|---|---|
| CLAIMABLE | 6 |
| TAKEN-NOT-YOURS | 4 |
| PROTECTED | 2 |
| SAFE | 9 |

## Findings

| Priority | Ecosystem | Name | Found in | Public status | Verdict | Action |
|---|---|---|---|---|---|---|
| CRITICAL | npm | `acmecorp-config-loader` | Dockerfile | unclaimed | **CLAIMABLE** | Defensively register this name on the public registry now (a stub you control), and reserve the npm scope / pin the pip index so builds cannot fall back to public. |
| CRITICAL | npm | `acmecorp-internal-logger` | ci | taken (mallory) | **TAKEN-NOT-YOURS** | Investigate: a public package with this name exists and is not yours (possible squat). Verify the owner and publish date; if malicious, report it to the registry and pin/replace the dependency. |
| CRITICAL | npm | `acmecorp-internal-ui` | package.json | unclaimed | **CLAIMABLE** | Defensively register this name on the public registry now (a stub you control), and reserve the npm scope / pin the pip index so builds cannot fall back to public. |
| CRITICAL | pypi | `acme-internal-auth` | requirements.txt | unclaimed | **CLAIMABLE** | Defensively register this name on the public registry now (a stub you control), and reserve the npm scope / pin the pip index so builds cannot fall back to public. |
| CRITICAL | pypi | `acme-internal-billing` | requirements.txt | unclaimed | **CLAIMABLE** | Defensively register this name on the public registry now (a stub you control), and reserve the npm scope / pin the pip index so builds cannot fall back to public. |
| CRITICAL | pypi | `acme-internal-telemetry-kit0` | requirements.txt | unclaimed | **CLAIMABLE** | Defensively register this name on the public registry now (a stub you control), and reserve the npm scope / pin the pip index so builds cannot fall back to public. |
| CRITICAL | pypi | `acme-internal-utils` | requirements.txt | taken (mallory) | **TAKEN-NOT-YOURS** | Investigate: a public package with this name exists and is not yours (possible squat). Verify the owner and publish date; if malicious, report it to the registry and pin/replace the dependency. |
| CRITICAL | pypi | `paymentsvc-core-kit0` | requirements.txt | unclaimed | **CLAIMABLE** | Defensively register this name on the public registry now (a stub you control), and reserve the npm scope / pin the pip index so builds cannot fall back to public. |
| HIGH | pypi | `acme-logging-legacy` | requirements.txt | taken (oss-maintainer) | **TAKEN-NOT-YOURS** | Investigate: a public package with this name exists and is not yours (possible squat). Verify the owner and publish date; if malicious, report it to the registry and pin/replace the dependency. |
| HIGH | pypi | `acme-tools` | requirements.txt | taken (thirdparty-dev) | **TAKEN-NOT-YOURS** | Investigate: a public package with this name exists and is not yours (possible squat). Verify the owner and publish date; if malicious, report it to the registry and pin/replace the dependency. |
| MEDIUM | npm | `@acme/payments` | package.json | unclaimed | **PROTECTED** | Exposure is mitigated by configuration (scope reserved / index pinned). Keep the config under review and re-scan in CI — a config change re-opens the exposure. |
| MEDIUM | npm | `@acme/secrets` | package.json | unclaimed | **PROTECTED** | Exposure is mitigated by configuration (scope reserved / index pinned). Keep the config under review and re-scan in CI — a config change re-opens the exposure. |
| INFO | npm | `acmecorp-widgets` | package.json | taken (acme) | **SAFE** | No action needed: the name is legitimately public (well-known or org-owned). |
| INFO | npm | `axios` | package.json | taken (community) | **SAFE** | No action needed: the name is legitimately public (well-known or org-owned). |
| INFO | npm | `chalk` | package.json | taken (community) | **SAFE** | No action needed: the name is legitimately public (well-known or org-owned). |
| INFO | npm | `datastore-sync-layer` | package.json | taken (mallory) | **SAFE** | No action needed: the name is legitimately public (well-known or org-owned). |
| INFO | npm | `express` | package.json | taken (community) | **SAFE** | No action needed: the name is legitimately public (well-known or org-owned). |
| INFO | pypi | `acme-sdk` | pyproject.toml | taken (acme) | **SAFE** | No action needed: the name is legitimately public (well-known or org-owned). |
| INFO | pypi | `flask` | requirements.txt | taken (community) | **SAFE** | No action needed: the name is legitimately public (well-known or org-owned). |
| INFO | pypi | `pydantic` | requirements.txt | taken (community) | **SAFE** | No action needed: the name is legitimately public (well-known or org-owned). |
| INFO | pypi | `requests` | requirements.txt | taken (community) | **SAFE** | No action needed: the name is legitimately public (well-known or org-owned). |

