#!/bin/bash
# Heimdall RAI hands-off bootstrap runner (runs on the in-VNet AML compute instance).
# Launched by the CI inline creation script via systemd-run as azureuser so it
# survives the setup-script cgroup teardown. Trains the ensemble, registers the
# datasets + MLflow model, and submits the Responsible AI pipeline. Progress is
# reported as MLflow tags on experiment 'rai-bootstrap-status' (watchable from the host).
LOG=/tmp/rai_bootstrap.log
exec > >(tee -a "$LOG") 2>&1
set -x

source /anaconda/etc/profile.d/conda.sh 2>/dev/null || true
conda activate azureml_py310_sdkv2 2>/dev/null || conda activate azureml_py38 2>/dev/null || true
export PATH="$HOME/.local/bin:$PATH"
PY=$(command -v python || command -v python3)
export CID=91d76e99-9ce1-47cb-92ec-6f101fce7d14

REPO="$HOME/FraudIntelligence"
RPT="$REPO/ml/rai_bootstrap/report.py"
report(){ "$PY" "$RPT" "$1" "${2:-1}" || true; }
trap '"$PY" "$RPT" logtail "$(tail -c 2500 "$LOG" | tr "\n" "~")" || true' EXIT

cd "$REPO" || { report repo_missing "$REPO"; exit 1; }
report start "py=$PY"

# Pin xgboost<3 so the model's conda env installs on the RAI env's Python 3.9
# (xgboost 3.x requires Python >=3.10, which breaks `conda env update` in the
# responsibleai-tabular env when the RAI constructor loads the model).
"$PY" -m pip install -q --user lightgbm "xgboost==2.1.4" skl2onnx onnxmltools onnxruntime mltable 2>&1 | tail -4
report pip done

"$PY" -m ml.train_ensemble --output ml/artifacts/ --smoke 60000 && report train ok || { report train FAILED; exit 3; }
"$PY" ml/rai_bootstrap/register_submit.py && report submit ok || { report submit FAILED; exit 4; }
report done
