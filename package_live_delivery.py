"""Package only the declared deliverables; never include uploaded raw logs."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
FILES = ["README.md", "requirements.txt", "MODEL_INTERFACE.md", "TESTING.md",
         "MODEL_DELIVERY_GUIDE.md", "MODEL_EVALUATION.md", "MODEL_RELEASE_2_2.md", "DEMO_DAY_2026.md",
         "output/presentations/NBE_Innovation_Cycle_2026_Final_Presentation.pptx",
         "output/pdf/NBE_Innovation_Cycle_2026_Self_Healing_Log_Intelligence_Report.pdf",
         "PROJECT_ROADMAP.md", "FEATURE_CATALOG.md", "DATASET_INVENTORY.md",
         "DATA_TIME_AND_FAILURE_POLICY.md", "INCIDENT_PREDICTION_PLAN.md",
         "LIVE_DEMO.md", "CROSS_SOURCE_LOGIC.md", "model_runtime.py",
         "build_corrected_dataset.py", "train_v2_models.py", "score_v2_system.py",
         "build_incident_targets.py", "run_model_demo.py", "failure_prediction.py", "forecast_policy.py",
         "raw_log_service.py", "cross_source_review.py", "package_live_delivery.py"]
DIRECTORIES = ["web", "schemas", "tests", "models_v2", "outputs_v2"]
SOURCE_ARCHIVE_OUTPUTS = {"diagnostic_records.csv.gz", "parsed_record_index.csv.gz", "parse_failures.csv.gz"}


if __name__ == "__main__":
    destination = ROOT / "release/Self_Healing_Live_Dashboard.zip"
    destination.parent.mkdir(exist_ok=True)
    paths = [ROOT / name for name in FILES]
    examples = ROOT / "examples"
    paths.extend(sorted(examples.glob("*.json")))
    paths.append(examples / "apache_demo.log")
    paths.extend(sorted((examples / "blind_apache_12_windows").glob("*.json")))
    for folder in DIRECTORIES:
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix != ".pyc"
                     and p.name not in SOURCE_ARCHIVE_OUTPUTS)
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
