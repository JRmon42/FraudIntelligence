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

* full FraudIntelligence platform (docs, infra, services, ml, slides) ([5cb7adc](https://github.com/JRmon42/FraudIntelligence/commit/5cb7adc70cdfc6c0067bd6b06e54558270e513fa))
