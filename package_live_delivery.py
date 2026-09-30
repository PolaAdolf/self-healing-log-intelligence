"""Package only the declared deliverables; never include uploaded raw logs."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
FILES = ["README.md", "requirements.txt", "MODEL_INTERFACE.md", "TESTING.md",
         "PROJECT_ROADMAP.md", "FEATURE_CATALOG.md", "DATASET_INVENTORY.md",
         "DATA_TIME_AND_FAILURE_POLICY.md", "INCIDENT_PREDICTION_PLAN.md",
         "LIVE_DEMO.md", "CROSS_SOURCE_LOGIC.md", "model_runtime.py",
         "build_corrected_dataset.py", "train_v2_models.py", "score_v2_system.py",
         "build_incident_targets.py", "run_model_demo.py", "failure_prediction.py",
         "raw_log_service.py", "cross_source_review.py", "package_live_delivery.py"]
DIRECTORIES = ["web", "schemas", "examples", "tests", "models_v2", "outputs_v2"]


if __name__ == "__main__":
    destination = ROOT / "release/Self_Healing_Live_Dashboard.zip"
    destination.parent.mkdir(exist_ok=True)
    paths = [ROOT / name for name in FILES]
    for folder in DIRECTORIES:
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix != ".pyc")
    temporary = destination.with_suffix(".zip.tmp")
    with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, Path("Self_Healing_Live_Dashboard") / path.relative_to(ROOT))
    with ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity check failed")
        print(f"Verified {len(archive.namelist())} files")
    temporary.replace(destination)
    print(destination)
