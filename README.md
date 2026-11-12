# Japan Post EMS Automation

A local Python and Playwright tool for preparing an EMS goods shipping label in Japan Post International Mail My-page on macOS.

[日本語](README.ja.md) · [中文操作说明](docs/usage.zh-CN.md)

## Why this project

International shipping requires entering recipient details, customs item information and dispatch settings across several screens. This project turns structured recipient and parcel JSON into a guided browser workflow for a recurring personal shipping task.

The working version was iterated against user-reported screens and manually exercised by the project owner. It is an independent personal project, unaffiliated with Japan Post.

## Features

- Optional local login credentials in macOS Keychain, or manual browser login.
- Existing sender selection preserved; recipient details read from JSON.
- EMS goods selection, one customs item, country dropdowns and item confirmation.
- Dispatch date set to the day after program startup in Japan time, including month/year boundaries.
- Draft recovery handling, multiple browser windows and page-state checks.
- Registration-attempt fingerprint saved before submission to reduce accidental duplicate labels.
- Diagnostic metadata for navigation failures, without collecting text-field values or request bodies.
- Stops after clicking the official print button; leaves the browser open for the user.

## Requirements

macOS, Python 3.10+, a supported Playwright browser environment, an internet connection, and an existing Japan Post International Mail My-page account. Terminal messages and CLI help are in English. Node.js is needed only for JavaScript tests.

## Run locally

Download or clone the repository and open Terminal in its directory:

```bash
# Optional: save credentials to macOS Keychain
bash setup_login.command

# Choose a recipient JSON file in the file picker
bash run.command

# Or provide its path directly
bash run.command /path/to/Recipient_Name.json
```

The launcher creates `.venv`, installs Python dependencies and downloads Chromium on first use. It controls a separate browser window. Complete any verification or site-specific error prompts manually, then follow the terminal instructions to resume.

`shipment.example.json` contains fictional data and is deliberately blocked from label creation. For actual use, copy it to a separate JSON file, replace all recipient and parcel details, and remove `_example`. Keep private data outside the repository. All amounts, quantities, weights, phone numbers and postal codes are strings.

```bash
bash run.command /path/to/Recipient_Name.json --validate-only
bash run.command /path/to/Recipient_Name.json --stop-before-register
bash run.command /path/to/Recipient_Name.json --manual-login
bash run.command --forget-login
```

`--stop-before-register` stops at the review screen without registering a label. A full run attempts registration and clicks `注意事項に同意して送り状を印刷` on the official print page, then stops. Press Enter in Terminal after finishing to close the automation browser. Clicking the website button does not establish that a physical printer completed printing.

## Data and declarations

The program handles one recipient and one item per run. JSON controls the actual item name, unit price, quantity, weight and gift/sale classification. Screenshots or free-form text must be converted to JSON separately; OCR and chat integration are not built into this application.

The public edition has no personal parcel defaults. Supply the actual origin explicitly; provide the appropriate HS code where required. Sample names, addresses, amounts and weights are synthetic placeholders. `000000` is a dummy HS value for offline tests, not a customs classification. Do not submit the example to the website. Confirm the actual contents and the website's dangerous-goods declaration before setting `noDangerousGoods` to `true`. Ship dates in JSON are overridden at runtime with the next day in Japan time.

## Duplicate prevention and privacy

Preserve `output/run-state.json` between runs and updates. It records an input fingerprint and registration-attempt time, not proof of successful registration. If interrupted after submission, check the official scheduled-shipment list before retrying. `--allow-repeat` is an explicit override after that check.

Credentials stay in the local macOS Keychain; the repository contains no account details. `.gitignore` excludes recipient JSON (except the fictional example), runtime output, screenshots, PDFs and local environments. Review diagnostic files before sharing them. Do not commit real customer information or browser sessions.

## Tests

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -v
node test_login.cjs
node test_content.cjs
node test_dispatch.cjs
```

The suite uses Python mocks and JavaScript DOM fixtures, covering navigation, image controls, item table layouts, date selection, Keychain handling, diagnostics, duplicate checks and the print stopping point. GitHub Actions runs these offline tests. CI does not log into Japan Post or validate live shipment creation.

## Code map

| Files | Responsibility |
| --- | --- |
| `japanpost.py` | Validation, orchestration, registration state and print endpoint |
| `credentials.py` | Local Keychain credentials |
| `page_state.py`, `diagnostics.py`, `action_audit.py` | Stage detection and failure evidence |
| `login.js`, `navigation.js` | Browser login and navigation helpers |
| `recipient.js`, `content.js`, `shipment.js` | Form filling and dispatch options |
| `test_*.py`, `test_*.cjs` | Offline regression tests |

## Limitations and development

The website can change, verification may need manual input, and unavailable destination services require user review. There is no unattended batch mode or guarantee against all duplicate registrations. The tested personal workflow preserves the currently selected sender.

Developed with AI assistance. The project owner supplied the workflow, requirements and shipping defaults, tested the application on macOS, and reported failures used to refine it. The repository documents an applied automation project; it does not claim independently hand-written authorship of every line.
