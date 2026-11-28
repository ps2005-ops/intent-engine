# Prospect-98: all 98 companies on one frozen tree (c2-7fa8ec5f, commit 69c19103)

P pass · b bounded · F fail. Hist-B = private-enterprise history standard (separate; never merged). B = strengthened intelligence view fully qualified; C = commercial view fully qualified.

```
{
 "companies": 98,
 "original_10of10": 0,
 "strengthened_B_fully": 6,
 "commercial_C_fully": 90,
 "mean": 8.133,
 "median": 8.5,
 "min": 5.5,
 "min_company": [
  "Ivalua"
 ],
 "decision_grade": 64,
 "pass_counts": {
  "search": 95,
  "identity": 97,
  "coverage": 87,
  "independence": 45,
  "economics": 5,
  "strategy": 64,
  "presentation": 54,
  "history": 13,
  "visual": 98,
  "performance": 98
 },
 "history_private_standard": {
  "PASS": 39,
  "BOUNDED": 27,
  "FAIL": 32
 },
 "by_category": {
  "C1": 8.232,
  "C2": 7.722,
  "C3": 8.286,
  "C4": 8.364
 },
 "by_split": {
  "DEVELOPMENT": 8.079,
  "VALIDATION": 8.321,
  "FINAL_UNTOUCHED": 8.214
 },
 "tree": "c2-7fa8ec5f (commit 69c19103)",
 "baseline_development_mean": 6.65
}
```

| # | Company | Cat | Split | Srch | Id | Cov | Ind | Econ | Strat | Pres | Hist | Hist-B | Vis | Perf | Score | B | C |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Alteryx | C1 | DEVEL | P | P | P | P | b | P | b | b | P | P | P | 8.5 |  | ✓ |
| 2 | Domo | C1 | DEVEL | P | P | b | P | b | P | b | b | b | P | P | 8.0 |  | ✓ |
| 3 | StarTree | C1 | DEVEL | P | P | P | b | b | P | b | b | P | P | P | 8.0 |  | ✓ |
| 4 | ClickHouse | C1 | DEVEL | P | P | P | P | b | P | b | b | b | P | P | 8.5 |  | ✓ |
| 5 | Firebolt | C1 | DEVEL | P | P | P | P | b | P | b | b | b | P | P | 8.5 |  | ✓ |
| 6 | MotherDuck | C1 | VALID | P | P | P | P | b | P | P | b | b | P | P | 9.0 |  | ✓ |
| 7 | Astronomer | C1 | FINAL | P | P | P | P | b | P | P | b | b | P | P | 9.0 |  | ✓ |
| 8 | FalkorDB | C1 | DEVEL | P | P | P | F | b | b | P | b | b | P | P | 7.5 |  | ✓ |
| 9 | Pinecone | C1 | DEVEL | P | P | P | P | b | P | b | b | P | P | P | 8.5 |  | ✓ |
| 10 | Weaviate | C1 | DEVEL | P | P | P | P | b | P | b | b | b | P | P | 8.5 |  | ✓ |
| 11 | Zilliz | C1 | DEVEL | P | P | P | b | b | P | P | b | b | P | P | 8.5 |  | ✓ |
| 12 | Glean | C1 | DEVEL | P | P | P | P | b | P | b | b | b | P | P | 8.5 |  | ✓ |
| 13 | Writer | C1 | DEVEL | P | P | P | P | b | P | P | b | P | P | P | 9.0 |  | ✓ |
| 14 | C3 AI | C1 | VALID | P | P | P | P | b | P | b | P | P | P | P | 9.0 |  | ✓ |
| 15 | Domino Data Lab | C1 | DEVEL | P | P | P | b | b | P | P | b | P | P | P | 8.5 |  | ✓ |
| 16 | Fiddler AI | C1 | DEVEL | P | P | P | P | b | P | P | b | F | P | P | 9.0 |  | ✓ |
| 17 | Arthur AI | C1 | DEVEL | P | P | P | P | b | P | P | b | F | P | P | 9.0 |  | ✓ |
| 18 | Tonic.ai | C1 | FINAL | P | F | P | b | b | F | b | b | F | P | P | 6.0 |  |  |
| 19 | Unstructured | C1 | DEVEL | P | P | P | F | b | b | b | b | F | P | P | 7.0 |  | ✓ |
| 20 | LandingAI | C1 | DEVEL | P | P | P | F | b | b | P | b | b | P | P | 7.5 |  | ✓ |
| 21 | Snorkel AI | C1 | DEVEL | P | P | P | P | b | P | b | b | P | P | P | 8.5 |  | ✓ |
| 22 | Labelbox | C1 | DEVEL | P | P | P | F | b | b | b | b | F | P | P | 7.0 |  | ✓ |
| 23 | Hyperscience | C1 | FINAL | P | P | P | P | b | P | b | b | P | P | P | 8.5 |  | ✓ |
| 24 | Alkymi | C1 | VALID | P | P | P | F | b | b | P | b | F | P | P | 7.5 |  | ✓ |
| 25 | Ocrolus | C1 | VALID | P | P | P | F | b | b | P | b | P | P | P | 7.5 |  | ✓ |
| 26 | Amplitude | C1 | FINAL | P | P | P | P | b | P | P | P | P | P | P | 9.5 | ✓ | ✓ |
| 27 | Pendo | C1 | DEVEL | P | P | P | F | b | b | b | b | b | P | P | 7.0 |  | ✓ |
| 28 | Fullstory | C1 | DEVEL | P | P | P | P | b | P | P | b | P | P | P | 9.0 |  | ✓ |
| 29 | Coupa | C2 | DEVEL | P | P | P | P | b | P | b | b | P | P | P | 8.5 |  | ✓ |
| 30 | JAGGAER | C2 | DEVEL | P | P | F | b | b | P | P | b | F | P | P | 7.5 |  |  |
| 31 | GEP | C2 | DEVEL | P | P | P | F | b | b | P | b | F | P | P | 7.5 |  | ✓ |
| 32 | Ivalua | C2 | DEVEL | P | P | F | F | b | b | b | F | F | P | P | 5.5 |  |  |
| 33 | Manhattan Associates | C2 | FINAL | P | P | P | b | b | P | b | P | P | P | P | 8.5 |  | ✓ |
| 34 | ToolsGroup | C2 | DEVEL | P | P | P | F | b | b | P | b | P | P | P | 7.5 |  | ✓ |
| 35 | Netstock | C2 | DEVEL | P | P | P | F | b | b | b | b | P | P | P | 7.0 |  | ✓ |
| 36 | SourceDay | C2 | FINAL | P | P | P | F | P | b | P | b | b | P | P | 8.0 |  | ✓ |
| 37 | LevaData | C2 | DEVEL | P | P | P | F | P | b | P | b | F | P | P | 8.0 |  | ✓ |
| 38 | Arkestro | C2 | DEVEL | P | P | P | F | b | b | P | b | b | P | P | 7.5 |  | ✓ |
| 39 | Fairmarkit | C2 | DEVEL | P | P | P | F | b | b | P | b | F | P | P | 7.5 |  | ✓ |
| 40 | Zip | C2 | DEVEL | P | P | P | b | b | P | b | b | F | P | P | 8.0 |  | ✓ |
| 41 | Order.co | C2 | VALID | P | P | F | F | b | b | P | b | F | P | P | 6.5 |  |  |
| 42 | Avetta | C2 | DEVEL | P | P | P | b | b | P | b | b | F | P | P | 8.0 |  | ✓ |
| 43 | RapidRatings | C2 | VALID | P | P | P | F | b | b | P | b | F | P | P | 7.5 |  | ✓ |
| 44 | Fusion Risk Management | C2 | DEVEL | P | P | P | F | b | b | b | b | b | P | P | 7.0 |  | ✓ |
| 45 | Riskonnect | C2 | DEVEL | P | P | P | P | b | P | P | b | P | P | P | 9.0 |  | ✓ |
| 46 | MetricStream | C2 | VALID | P | P | P | P | b | P | b | b | P | P | P | 8.5 |  | ✓ |
| 47 | NAVEX | C2 | DEVEL | P | P | P | F | b | b | b | b | F | P | P | 7.0 |  | ✓ |
| 48 | SAFE | C2 | FINAL | P | P | P | F | b | b | P | b | F | P | P | 7.5 |  | ✓ |
| 49 | KPA | C2 | DEVEL | P | P | P | F | b | b | P | b | F | P | P | 7.5 |  | ✓ |
| 50 | RANE | C2 | DEVEL | P | P | P | F | b | b | P | b | F | P | P | 7.5 |  | ✓ |
| 51 | Eurasia Group | C2 | DEVEL | P | P | F | F | b | b | P | b | F | P | P | 6.5 |  |  |
| 52 | Oxford Economics | C2 | DEVEL | P | P | F | b | b | P | P | b | F | P | P | 7.5 |  |  |
| 53 | Gartner | C2 | DEVEL | P | P | P | P | b | P | b | P | P | P | P | 9.0 |  | ✓ |
| 54 | Forrester | C2 | VALID | P | P | P | P | b | P | P | P | P | P | P | 9.5 | ✓ | ✓ |
| 55 | CB Insights | C2 | FINAL | P | P | P | P | b | P | P | b | b | P | P | 9.0 |  | ✓ |
| 56 | OneStream | C3 | FINAL | P | P | P | P | b | P | b | b | b | P | P | 8.5 |  | ✓ |
| 57 | insightsoftware | C3 | DEVEL | P | P | P | b | b | P | b | b | F | P | P | 8.0 |  | ✓ |
| 58 | Prophix | C3 | DEVEL | P | P | b | P | b | P | P | b | b | P | P | 8.5 |  | ✓ |
| 59 | cfo.ai | C3 | VALID | P | P | P | b | b | P | P | b | P | P | P | 8.5 |  | ✓ |
| 60 | Drivetrain | C3 | DEVEL | P | P | b | P | b | P | P | b | F | P | P | 8.5 |  |  |
| 61 | Abacum | C3 | DEVEL | P | P | P | F | b | b | P | b | b | P | P | 7.5 |  | ✓ |
| 62 | Maxio | C3 | DEVEL | P | P | P | F | b | b | P | b | P | P | P | 7.5 |  | ✓ |
| 63 | Chargebee | C3 | DEVEL | P | P | P | b | P | P | P | b | F | P | P | 9.0 |  | ✓ |
| 64 | Deltek | C3 | DEVEL | P | P | P | P | b | P | P | b | P | P | P | 9.0 |  | ✓ |
| 65 | ECI Software Solutions | C3 | DEVEL | P | P | P | F | b | b | P | b | P | P | P | 7.5 |  | ✓ |
| 66 | Aptean | C3 | DEVEL | P | P | P | P | P | P | b | b | b | P | P | 9.0 |  | ✓ |
| 67 | SYSPRO | C3 | VALID | P | P | P | F | b | b | P | b | b | P | P | 7.5 |  | ✓ |
| 68 | Appian | C3 | VALID | P | P | P | P | b | P | b | P | P | P | P | 9.0 |  | ✓ |
| 69 | Pegasystems | C3 | DEVEL | P | P | P | P | b | P | P | P | P | P | P | 9.5 | ✓ | ✓ |
| 70 | Celonis | C3 | DEVEL | b | P | P | b | b | P | b | b | F | P | P | 7.5 |  | ✓ |
| 71 | Kissflow | C3 | DEVEL | P | P | P | F | b | b | P | b | P | P | P | 7.5 |  | ✓ |
| 72 | Tonkean | C3 | FINAL | P | P | P | F | b | b | b | b | F | P | P | 7.0 |  | ✓ |
| 73 | Nintex | C3 | DEVEL | P | P | P | b | b | P | b | b | P | P | P | 8.0 |  | ✓ |
| 74 | UiPath | C3 | DEVEL | P | P | P | P | b | P | P | P | P | P | P | 9.5 | ✓ | ✓ |
| 75 | Kantata | C3 | DEVEL | P | P | P | P | b | P | P | b | b | P | P | 9.0 |  | ✓ |
| 76 | HighRadius | C3 | FINAL | P | P | P | b | b | P | b | b | P | P | P | 8.0 |  | ✓ |
| 77 | SecurityScorecard | C4 | DEVEL | P | P | P | P | b | P | b | b | b | P | P | 8.5 |  | ✓ |
| 78 | BitSight | C4 | DEVEL | P | P | b | P | b | P | b | b | P | P | P | 8.0 |  | ✓ |
| 79 | Censys | C4 | DEVEL | P | P | P | P | b | P | b | b | b | P | P | 8.5 |  | ✓ |
| 80 | Wiz | C4 | DEVEL | P | P | P | P | b | P | b | b | b | P | P | 8.5 |  | ✓ |
| 81 | Aqua Security | C4 | DEVEL | P | P | P | P | b | P | b | b | P | P | P | 8.5 |  | ✓ |
| 82 | Sysdig | C4 | FINAL | b | P | b | P | b | P | b | b | b | P | P | 7.5 |  | ✓ |
| 83 | Tenable | C4 | VALID | P | P | P | P | b | P | P | P | P | P | P | 9.5 | ✓ | ✓ |
| 84 | Rapid7 | C4 | FINAL | P | P | P | P | b | P | P | P | P | P | P | 9.5 | ✓ | ✓ |
| 85 | SentinelOne | C4 | DEVEL | P | P | P | P | b | P | b | P | P | P | P | 9.0 |  | ✓ |
| 86 | Claroty | C4 | DEVEL | b | P | P | P | b | P | b | b | P | P | P | 8.0 |  | ✓ |
| 87 | Forescout | C4 | DEVEL | P | P | P | P | b | P | b | b | P | P | P | 8.5 |  | ✓ |
| 88 | Corelight | C4 | DEVEL | P | P | P | P | b | P | P | b | b | P | P | 9.0 |  | ✓ |
| 89 | Critical Start | C4 | FINAL | P | P | P | b | b | P | P | b | F | P | P | 8.5 |  | ✓ |
| 90 | ePlus | C4 | VALID | P | P | P | F | b | b | P | P | P | P | P | 8.0 |  | ✓ |
| 91 | SHI International | C4 | DEVEL | P | P | F | b | b | P | P | b | F | P | P | 7.5 |  |  |
| 92 | Insight Enterprises | C4 | VALID | P | P | P | b | P | P | b | P | P | P | P | 9.0 |  | ✓ |
| 93 | Concentric AI | C4 | DEVEL | P | P | P | P | b | P | P | b | P | P | P | 9.0 |  | ✓ |
| 94 | Improving | C4 | DEVEL | P | P | P | F | b | b | P | b | F | P | P | 7.5 |  | ✓ |
| 95 | Launch Consulting | C4 | DEVEL | P | P | P | F | b | b | P | b | F | P | P | 7.5 |  | ✓ |
| 96 | Sparq | C4 | DEVEL | P | P | P | b | b | P | P | b | b | P | P | 8.5 |  | ✓ |
| 97 | Bounteous | C4 | DEVEL | P | P | P | F | b | b | b | b | F | P | P | 7.0 |  | ✓ |
| 98 | SoftServe | C4 | DEVEL | P | P | P | b | b | P | P | b | F | P | P | 8.5 |  | ✓ |
