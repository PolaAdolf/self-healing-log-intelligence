# Public repository privacy review

Read-only pattern review of tracked text on 26 November 2026. No raw lines or matched identifiers are reproduced below. Patterns can match versions or illustrative configuration. This is not a guarantee that all private information is absent. Binary models and historical recordings need owner review before wider promotion.

## Synthetic demonstration

`examples/apache_demo.log` uses documentation-range IP addresses. The file is the repository’s synthetic demonstration, not customer telemetry. Screenshots and `demo_result.json` use only this sample. The model data is aggregated; no raw customer input was added.

## Matches requiring context

| File | IPv4 candidates outside example/loopback ranges | Email patterns | Local user path |
| --- | ---: | ---: | --- |
| `tests/test_corrected_dataset.py` | 1 | 0 | False |

No source data was silently removed. Historical videos have been removed from the current branch and remain in earlier Git history. A history rewrite would require a separate owner decision. Public distribution of bank-related material, including older binaries, remains an owner review item.

The only IPv4 candidate outside documentation/loopback ranges is a hard-coded private-address string in a unit-test fixture (`tests/test_corrected_dataset.py:47`). It is constructed in the test, not extracted from customer data. It was retained and documented, with no production code or fixture behavior change.
