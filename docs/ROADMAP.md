# WarRoom v2 roadmap

WarRoom v1 proves three OWASP bugs can be exploited and defended. v2 turns it
into a measured purple-team range: every offensive technique has a matching
detection, and a neutral referee scores both sides on outcomes that mirror how
a real SOC is judged.

## Goals, and the frameworks they map to

| Dimension | Anchored to | What it demonstrates |
|---|---|---|
| Attack-surface breadth | OWASP Top 10 (2021) | Coverage of the real vuln landscape |
| Full attack lifecycle | MITRE ATT&CK tactics | Recon → exfil as a chain, not point exploits |
| Detection maturity | Pyramid of Pain, Sigma, detection-as-code | Catching behaviour, not just literal payloads |
| Response discipline | NIST SP 800-61 IR lifecycle; MTTD / MTTR / dwell time | Measuring and improving, like a SOC |

## Roles

- **Target** (`services/target_app`) — the vulnerable app, now scenario-driven.
- **Red** (`agents/red_team`) — attack lifecycle, lab-locked to the range.
- **Blue** (`agents/blue_team`) — detection-as-code + graduated response.
- **Referee** (`services/referee`) — neutral authority: flag oracle, rounds,
  scoring, independent SLA probe, after-action reports.
- **Dashboard** (`dashboard`) — live view of the match.

## Phases

Each phase is independently mergeable and leaves the suite green.

### Phase 0 — isolation + CI
- Confine the range to an `internal` Docker network so the command-injection
  path cannot reach off-host (closes the v1 egress finding, CWE-923). Published
  loopback ports stay for the UI and dashboard.
- Add GitHub Actions CI that runs the full suite on every push/PR.

### Phase 1 — the Referee
- Neutral flag oracle: the referee mints and validates flags; the target only
  leaks them and no longer scores itself.
- Match/round engine, scoring rubric as config, independent SLA prober,
  append-only match journal, and an after-action report per match.

### Phase 2 — detection-as-code
- Blue signatures move to Sigma-style rule files, each carrying severity and a
  MITRE technique id, loaded and unit-tested.
- MTTD / MTTR / dwell-time metrics computed from the match journal.

### Phase 3 — scenario engine + new vulns
- `scenarios/*.yaml` select enabled vulns, difficulty, and seeded data.
- Add IDOR (A01) and SSRF (A10, reaching an internal-only metadata service),
  each with red exploit, blue detection, and referee flag.

### Phase 4 — kill-chain + stealth
- Red campaign runner chains techniques (e.g. SSRF → metadata → credential →
  auth bypass) scored as a multi-stage campaign.
- `--profile stealth|loud` changes timing/shape so stealth can be scored.
- ATT&CK coverage view on the dashboard.

### Phase 5 — detection depth
- Honeytokens / decoy endpoints (high-fidelity detections).
- Behavioural detection (rate baselining, rare-endpoint access, recon→exploit
  sequences) beyond literal signatures.
- Graduated response playbooks: observe → throttle → virtual-patch → block.

### Phase 6 — fill the matrix
- New vuln classes: SSTI (A03) and JWT `alg=none` (A07/A02), each with red
  exploit, blue signature, and referee flag — chosen first because they add
  genuinely new OWASP categories.
- A living capability matrix (`docs/CAPABILITY_MATRIX.md`): technique ×
  detection × mitigation.
- Path traversal and blind/time-based SQLi are documented as the next
  scenarios in the matrix; they overlap the existing file-read and injection
  classes, so they add less new coverage per line and are deferred.

## Scoring model

```
red  = Σ_vector [ base + speed_bonus(t_capture) + stealth_bonus(if undetected) ]
blue = Σ_vector [ detect_bonus·decay(t_detect) + mitigate_bonus·decay(t_mitigate) ]
       + sla_uptime·w_sla  −  fp_penalty·fp_count
```

Speed and dwell-time terms are what teach the real SOC metrics; the SLA and
false-positive terms stop blue from "winning" by breaking or over-blocking the
service.
