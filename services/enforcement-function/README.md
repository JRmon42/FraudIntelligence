# enforcement-function

Async **enforcement consumer** for the Heimdall high-risk action path. Triggered
by the Service Bus `highrisk-alerts` queue; takes the durable action that must
stay **out** of the 18 ms synchronous scoring budget.

| Scoring decision | Enforcement actions |
|---|---|
| `DECLINE` | `block_card`, `open_case`, `notify_customer` |
| `STEP_UP` | `enforce_sca` |
| `MANUAL_REVIEW` | `open_case`, `notify_customer` |

## Runtime

* **Host:** Azure Functions v4, Python 3.11, Consumption (Y1) plan — provisioned by
  `infra/modules/functions.bicep`.
* **Trigger connection:** identity-based (`ServiceBusConnection__fullyQualifiedNamespace`
  + `ServiceBusConnection__credential=managedidentity`). The app's managed identity
  is granted **Azure Service Bus Data Receiver** by `infra/modules/servicebus.bicep`.
* **Case store (optional):** if `COSMOS_ENDPOINT` is set, cases are upserted to
  `fraud`/`cases` via `DefaultAzureCredential`.

## Deploy the code

Infra (the Function app shell) is created by Bicep. Publish the code with:

```bash
./scripts/deploy-enforcement.sh          # zip-deploy to func-heimdall-enforce-prod-swc
```

## Test

```bash
pip install -r requirements.txt pytest
pytest services/enforcement-function/tests -q
```
