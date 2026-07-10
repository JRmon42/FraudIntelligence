"""Register the RAI train/test MLTable datasets + the sklearn MLflow model, then
submit the Responsible AI pipeline (ml/aml_jobs/rai_scorecard.yml).

Runs on the in-VNet compute instance (data-plane uploads only work inside the
managed VNet). Auth via the attached UAMI. Assumes ml.train_ensemble has already
produced ml/artifacts/{sklearn-model, train_data.parquet, test_data.parquet}.
"""
import shutil
import pathlib

from azure.identity import ManagedIdentityCredential
from azure.ai.ml import MLClient, load_job
from azure.ai.ml.entities import Data, Model
from azure.ai.ml.constants import AssetTypes

CID = "91d76e99-9ce1-47cb-92ec-6f101fce7d14"
SUB = "ea8d83f8-8538-4914-ae12-24f954d61638"
RG = "heimdall_rg"
WS = "mlw-heimdall-prod-swc"

ml = MLClient(ManagedIdentityCredential(client_id=CID), SUB, RG, WS)

base = "ml/aml_jobs/rai_data"
for split in ("train", "test"):
    d = pathlib.Path(base) / split
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile("ml/artifacts/%s_data.parquet" % split, d / ("%s_data.parquet" % split))
    (d / "MLTable").write_text(
        "paths:\n  - file: ./%s_data.parquet\ntransformations:\n  - read_parquet\n" % split
    )

tr = ml.data.create_or_update(
    Data(name="fraud-intel-rai-train", path=base + "/train", type=AssetTypes.MLTABLE)
)
print("data train v", tr.version)
te = ml.data.create_or_update(
    Data(name="fraud-intel-rai-test", path=base + "/test", type=AssetTypes.MLTABLE)
)
print("data test v", te.version)
mo = ml.models.create_or_update(
    Model(
        name="fraud-intel-ensemble-sklearn",
        path="ml/artifacts/sklearn-model",
        type=AssetTypes.MLFLOW_MODEL,
    )
)
print("model v", mo.version)

job = load_job("ml/aml_jobs/rai_scorecard.yml")
model_info = "%s:%s" % (mo.name, mo.version)
try:
    job.inputs.model_info = model_info
except Exception:
    job.inputs["model_info"] = model_info

j = ml.jobs.create_or_update(job)
print("SUBMITTED_JOB", j.name)
open("/tmp/submitted_job", "w").write(j.name)
