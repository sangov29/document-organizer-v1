# Live frozen-corpus capture

This tool captures the application's live OCR and analysis output without
scoring or changing the corpus. It must run on a clean, verified `main` tree
against a scratch database.

## Prepare the input folder

Create one folder containing only the 12 frozen corpus documents. Nested files
are ignored. The tool rejects any count other than 12 and processes a filename
containing `annual` last, so a slow annual report cannot block the other eleven.

## Run

From the repository root in PowerShell:

```powershell
$corpus = "C:\path\to\frozen-12-documents"
$output = Join-Path (Split-Path $PWD -Parent) "document-organizer-live-capture"
New-Item -ItemType Directory -Force $output | Out-Null

docker compose run --rm -it `
  -v "${PWD}:/workspace" `
  -v "${corpus}:/corpus:ro" `
  -v "${output}:/output" `
  -w /workspace `
  backend python evaluation/capture_live_corpus.py `
    --api-url http://backend:8000/api/v1 `
    --documents-dir /corpus `
    --output-dir /output
```

Enter the scratch account email and password only at the prompts. Do not place
the password in the command or save it in the repository.

The output folder is deliberately outside the Git repository. The capture
refuses to run unless the repository is clean and checked out on `main`.

## Output and handling

`live-capture-output/raw-capture.json` contains the combined evidence. A
separate per-document JSON is updated after each document, so completed work is
preserved if a later document stalls.

The capture contains:

- the exact Git commit and branch;
- document IDs, filenames, statuses, and page counts;
- masked `/analysis` output;
- `/ocr` blocks, pixel boxes, and processed-image dimensions;
- a separate reveal pass with revealed sensitive values;
- explicit failure/timeout details without blocking later scoring.

The JSON contains revealed sensitive data. Keep it private and transmit it only
through the approved evidence channel. After the artifact is safely copied,
tear down the scratch stack and its volumes:

```powershell
docker compose down -v
```

Do not run the reveal pass against a canonical or production database because
each reveal creates an audit event.
