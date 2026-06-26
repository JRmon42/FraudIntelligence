## [1.8.0](https://github.com/JRmon42/FraudIntelligence/compare/v1.7.1...v1.8.0) (2026-06-26)

### Features

* **infra:** grant human/auditor principals Cosmos data-plane access ([2ee2109](https://github.com/JRmon42/FraudIntelligence/commit/2ee2109585f06682ebc0cd412562e3a86d8a3279))

## [1.7.1](https://github.com/JRmon42/FraudIntelligence/compare/v1.7.0...v1.7.1) (2026-06-25)

### Bug Fixes

* **infra:** don't link empty Azure Monitor private DNS zones to the VNet ([39ca4f8](https://github.com/JRmon42/FraudIntelligence/commit/39ca4f805c15137402e92884baee540cfc28810d))

## [1.7.0](https://github.com/JRmon42/FraudIntelligence/compare/v1.6.2...v1.7.0) (2026-06-25)

### Features

* **scoring-api:** export request telemetry to App Insights for audit ([813db68](https://github.com/JRmon42/FraudIntelligence/commit/813db688583ace5e4e5d1d017130b32183583770))

## [1.6.2](https://github.com/JRmon42/FraudIntelligence/compare/v1.6.1...v1.6.2) (2026-06-24)

### Bug Fixes

* **powerbi:** type Dim_Date[Date] as dateTime so DATEADD works ([da5c08d](https://github.com/JRmon42/FraudIntelligence/commit/da5c08def8a646ce1e5f488dcd6505ec6d6e94a5)), closes [#datetime](https://github.com/JRmon42/FraudIntelligence/issues/datetime)

## [1.6.1](https://github.com/JRmon42/FraudIntelligence/compare/v1.6.0...v1.6.1) (2026-06-24)

### Bug Fixes

* **powerbi:** use visualContainerObjects.title instead of invalid 'title' prop ([d700c19](https://github.com/JRmon42/FraudIntelligence/commit/d700c19c4cc0fb2267bffb688219163cdf02e7e5))

## [1.6.0](https://github.com/JRmon42/FraudIntelligence/compare/v1.5.1...v1.6.0) (2026-06-24)

### Features

* add 8-minute demo walkthrough video generator ([e1424df](https://github.com/JRmon42/FraudIntelligence/commit/e1424df91537f09ce17f2a7e4aa1fadeee4eb558))
* **powerbi:** add SCA, Channel & Country breakdowns to EBA Quarterly Report ([5f016fc](https://github.com/JRmon42/FraudIntelligence/commit/5f016fc0fe8eba63634abd64e6de22e4f9fc0333))

### Bug Fixes

* Power BI drift chart & measures + add EBA slicer and KPI visuals ([4178926](https://github.com/JRmon42/FraudIntelligence/commit/417892619bfe27a87a6b4e74d5a95d2d9a782719))
* **powerbi:** wrap multi-line Model Drift Index measure in TMDL backticks ([5237f4d](https://github.com/JRmon42/FraudIntelligence/commit/5237f4d3571eb5dac3fb33f5f5c541659e018b89))

## [1.5.1](https://github.com/JRmon42/FraudIntelligence/compare/v1.5.0...v1.5.1) (2026-06-19)

### Bug Fixes

* make R3 ACR readiness check private-endpoint aware + document CI tradeoff ([845c62e](https://github.com/JRmon42/FraudIntelligence/commit/845c62ead17ecd61f39f92d9e31c2bcc56e6d421))

## [1.5.0](https://github.com/JRmon42/FraudIntelligence/compare/v1.4.0...v1.5.0) (2026-06-19)

### Features

* make deployment production-ready & fully variabilized ([1d6c742](https://github.com/JRmon42/FraudIntelligence/commit/1d6c7424432abfdd1c061714407e2031888eac2a))

## [1.4.0](https://github.com/JRmon42/FraudIntelligence/compare/v1.3.0...v1.4.0) (2026-06-18)

### Features

* **scoring-api:** redirect root path to /docs ([2ce3501](https://github.com/JRmon42/FraudIntelligence/commit/2ce350153533adcc7b5dbe0dd1884fba2828bb20))

## [1.3.0](https://github.com/JRmon42/FraudIntelligence/compare/v1.2.0...v1.3.0) (2026-06-16)

### Features

* extend exec briefing + harden scale/resilience/security + ops dashboard ([09576c6](https://github.com/JRmon42/FraudIntelligence/commit/09576c69a3ed875875f6bde6e51a7bff7942df23))

## [1.2.0](https://github.com/JRmon42/FraudIntelligence/compare/v1.1.0...v1.2.0) (2026-06-15)

### Features

* **demo:** add decision-spectrum scenarios (approve / SCA step-up / decline) ([744385b](https://github.com/JRmon42/FraudIntelligence/commit/744385ba075ee7417b152fe134e5dad4b096111a))

## [1.1.0](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.14...v1.1.0) (2026-06-15)

### Features

* **demo:** add real-time web console for the live demo ([1393a34](https://github.com/JRmon42/FraudIntelligence/commit/1393a346785c1db2908a4ea6b017f7d910ce6c2e))

### Bug Fixes

* **scripts:** handle autoscale Cosmos containers in scale-to-min ([66e257f](https://github.com/JRmon42/FraudIntelligence/commit/66e257f1d02b9cf86699b5e434924262da1a4160))
* **smoke-test:** hit /healthz (not /health) — matches scoring-api route ([9bd8763](https://github.com/JRmon42/FraudIntelligence/commit/9bd8763d88ee714469d141da1c8a3b4ae553f2a6))

## [1.0.15](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.14...v1.0.15) (2026-06-12)

### Bug Fixes

* **scripts:** handle autoscale Cosmos containers in scale-to-min ([66e257f](https://github.com/JRmon42/FraudIntelligence/commit/66e257f1d02b9cf86699b5e434924262da1a4160))
* **smoke-test:** hit /healthz (not /health) — matches scoring-api route ([9bd8763](https://github.com/JRmon42/FraudIntelligence/commit/9bd8763d88ee714469d141da1c8a3b4ae553f2a6))

## [1.0.15](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.14...v1.0.15) (2026-06-12)

### Bug Fixes

* **smoke-test:** hit /healthz (not /health) — matches scoring-api route ([9bd8763](https://github.com/JRmon42/FraudIntelligence/commit/9bd8763d88ee714469d141da1c8a3b4ae553f2a6))

## [1.0.15](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.14...v1.0.15) (2026-06-12)

### Bug Fixes

* **smoke-test:** hit /healthz (not /health) — matches scoring-api route ([9bd8763](https://github.com/JRmon42/FraudIntelligence/commit/9bd8763d88ee714469d141da1c8a3b4ae553f2a6))

## [1.0.15](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.14...v1.0.15) (2026-06-12)

### Bug Fixes

* **smoke-test:** hit /healthz (not /health) — matches scoring-api route ([9bd8763](https://github.com/JRmon42/FraudIntelligence/commit/9bd8763d88ee714469d141da1c8a3b4ae553f2a6))

## [1.0.15](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.14...v1.0.15) (2026-06-12)

### Bug Fixes

* **smoke-test:** hit /healthz (not /health) — matches scoring-api route ([9bd8763](https://github.com/JRmon42/FraudIntelligence/commit/9bd8763d88ee714469d141da1c8a3b4ae553f2a6))

## [1.0.15](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.14...v1.0.15) (2026-06-12)

### Bug Fixes

* **smoke-test:** hit /healthz (not /health) — matches scoring-api route ([9bd8763](https://github.com/JRmon42/FraudIntelligence/commit/9bd8763d88ee714469d141da1c8a3b4ae553f2a6))

## [1.0.14](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.13...v1.0.14) (2026-05-13)

### Bug Fixes

* **scoring-api:** add async-timeout to deps ([77e0a7b](https://github.com/JRmon42/FraudIntelligence/commit/77e0a7b4173014c8b06e74a4460b7061fe3560da))

## [1.0.13](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.12...v1.0.13) (2026-05-13)

### Bug Fixes

* **scoring-api:** set PYTHONPATH so distroless python finds venv packages ([e047e7b](https://github.com/JRmon42/FraudIntelligence/commit/e047e7be1712949d485462db406063a07ca411fd))

## [1.0.12](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.11...v1.0.12) (2026-05-13)

### Bug Fixes

* **infra:** v15 - serialize defender pricings via dependsOn chain ([2affa67](https://github.com/JRmon42/FraudIntelligence/commit/2affa67f9a2d297fbb7e2368c6869f1853b74853))

## [1.0.11](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.10...v1.0.11) (2026-05-13)

### Bug Fixes

* **infra,eba:** v13 - serialize OAI PE after model deployments; install eba wheels as root ([58478d4](https://github.com/JRmon42/FraudIntelligence/commit/58478d444ca0fcda40c492f9de11982431139841))

## [1.0.10](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.9...v1.0.10) (2026-05-13)

### Bug Fixes

* **eba-reporter:** chown /wheels to non-root before pip install ([e33cc2b](https://github.com/JRmon42/FraudIntelligence/commit/e33cc2bd78758acb9345d956f500d4dd7d1dfa56))

## [1.0.9](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.8...v1.0.9) (2026-05-13)

### Bug Fixes

* **infra,eba:** v10 - single Purview RG Reader RA, install shadow-utils in eba ([b1341b3](https://github.com/JRmon42/FraudIntelligence/commit/b1341b36ad7036eb639ea3e2123f5a399598bca5))

## [1.0.8](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.7...v1.0.8) (2026-05-13)

### Bug Fixes

* **infra,eba:** v9 - drop unsupported AML alert, unique purview RA guids, no pip upgrade ([05a4cf2](https://github.com/JRmon42/FraudIntelligence/commit/05a4cf2d815195b74709f28e80d13788ea8b1403))

## [1.0.7](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.6...v1.0.7) (2026-05-13)

### Bug Fixes

* **infra:** v8 - keep ACR public, fix metric alerts, drop purview managedEventHubState ([2048105](https://github.com/JRmon42/FraudIntelligence/commit/204810550daff1569f4c2cb87536879925dcaeec))

## [1.0.6](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.5...v1.0.6) (2026-05-12)

### Bug Fixes

* **eba-reporter:** use python3/pip3 (Azure Linux base has no python alias) ([68d105b](https://github.com/JRmon42/FraudIntelligence/commit/68d105b85941a56e2dc354e30fe0d0501f85cc8b))

## [1.0.5](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.4...v1.0.5) (2026-05-12)

### Bug Fixes

* **infra:** merge AFD security policies (one WAF -> one securityPolicy) ([32000df](https://github.com/JRmon42/FraudIntelligence/commit/32000dfb269e421154bdfcb74141b64c19420abb))

## [1.0.4](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.3...v1.0.4) (2026-05-12)

### Bug Fixes

* **infra:** cosmos SQL-only + drop ACA service-tag IP rule ([650eaac](https://github.com/JRmon42/FraudIntelligence/commit/650eaacc4e0e6b0b857ec3c0b5f036eb082113d7))

## [1.0.3](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.2...v1.0.3) (2026-05-12)

### Bug Fixes

* **infra:** ACA OTel schema + Cosmos DR AZ unavailability ([242402a](https://github.com/JRmon42/FraudIntelligence/commit/242402a49ef11761ef719414ce402b826df65609))

## [1.0.2](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.1...v1.0.2) (2026-05-12)

### Bug Fixes

* **infra:** make regions independent + remove broken policy assignments ([053f008](https://github.com/JRmon42/FraudIntelligence/commit/053f008e878cb2b90a1117fa6b83e432e9e1dd3e))

## [1.0.1](https://github.com/JRmon42/FraudIntelligence/compare/v1.0.0...v1.0.1) (2026-05-12)

### Bug Fixes

* **infra:** bicep compile errors - secure LA shared key + dedupe [@secure](https://github.com/secure) decorator ([72e104b](https://github.com/JRmon42/FraudIntelligence/commit/72e104b9db15626affc85bea48181c7d41e81f72))

## 1.0.0 (2026-05-12)

### Features

* full Heimdall platform (docs, infra, services, ml, slides) ([5cb7adc](https://github.com/JRmon42/FraudIntelligence/commit/5cb7adc70cdfc6c0067bd6b06e54558270e513fa))
