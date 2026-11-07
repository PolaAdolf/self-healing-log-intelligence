# Blind Apache model-input sequence (synthetic)

These 12 files are **synthetic five-minute feature windows**, not original IT log files and not a real-world accuracy test. They are only for exercising the model's sequential history behavior.

## Run in GitHub Codespaces

From the repository root, run:

```bash
mkdir -p tmp/blind_apache_run
for n in $(seq -w 1 12); do
  python model_runtime.py \
    --input "examples/blind_apache_12_windows/window_${n}.json" \
    --output "tmp/blind_apache_run/result_${n}.json" \
    --state "tmp/blind_apache_run/state.json" >/dev/null || exit 1
done
cat tmp/blind_apache_run/result_12.json
```

Use the **same state file** for all 12 calls and keep the files in timestamp order. Do not run any file twice with that state. The first 11 calls should be history warm-up; the 12th should return the first scored window. The forecast fields, if present, are experimental scores, not incident probabilities.

The files contain feature summaries rather than raw Apache text logs. The raw-log dashboard accepts original Apache/IIS/Event Viewer files; this sequence is for the one-window model CLI (`model_runtime.py`).

