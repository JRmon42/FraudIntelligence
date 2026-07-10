"""Report bootstrap progress as MLflow tags on experiment 'rai-bootstrap-status'.

Runs on the in-VNet compute instance so the WSL host can watch progress via the
workspace MLflow tracking URI. Uses the attached UAMI (client id below) for auth.
Never raises: any failure is logged to /tmp/report.err so it cannot break the run.
"""
import sys
import os
import datetime

CID = "91d76e99-9ce1-47cb-92ec-6f101fce7d14"
SUB = "ea8d83f8-8538-4914-ae12-24f954d61638"
RG = "heimdall_rg"
WS = "mlw-heimdall-prod-swc"

try:
    import mlflow
    from azure.identity import ManagedIdentityCredential
    from azure.ai.ml import MLClient

    os.environ["AZURE_CLIENT_ID"] = CID
    ml = MLClient(ManagedIdentityCredential(client_id=CID), SUB, RG, WS)
    mlflow.set_tracking_uri(ml.workspaces.get(WS).mlflow_tracking_uri)
    mlflow.set_experiment("rai-bootstrap-status")

    run_id = ""
    try:
        run_id = open("/tmp/rai_run_id").read().strip()
    except Exception:
        pass
    if run_id:
        mlflow.start_run(run_id=run_id)
    else:
        r = mlflow.start_run(run_name="bootstrap")
        open("/tmp/rai_run_id", "w").write(r.info.run_id)

    key = sys.argv[1] if len(sys.argv) > 1 else "note"
    val = (sys.argv[2] if len(sys.argv) > 2 else "1")[:4900]
    mlflow.set_tag(key, val)
    mlflow.set_tag("last_stage", key)
    mlflow.set_tag("ts", datetime.datetime.utcnow().isoformat())
    mlflow.end_run()
except Exception as e:  # noqa: BLE001 - reporting must never break the bootstrap
    open("/tmp/report.err", "a").write("ERR %r\n" % e)
