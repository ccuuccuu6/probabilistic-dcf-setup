# Probabilistic DCF — first project setup

Start here. This project establishes one reusable Python workspace for many companies, with shared research such as coffee and FX. Nestlé is the first planned financial model. Keurig Dr Pepper is a future company configuration placeholder.

This is a setup package, not a completed financial model or data platform. It contains no live market data, calibrated probabilities, investment forecasts or AI API integration. It does not change anything on your computer until you download and run it.

## 1. What sits where

| Component | Initial location | Purpose |
|---|---|---|
| Project code | Your computer, edited in VS Code | Equations, validation, shared factor calculations and workflows |
| Code history | One private GitHub repository | Preserve changes to code, definitions and documentation |
| Research data | Git-ignored `local_store/` on your computer | Future original documents, observations and assumption versions |
| Run results | Git-ignored `outputs/` on your computer | Frozen scenario data, manifests and later Excel review workbooks |
| Execution | Your computer | Python runs when you issue a command |

GitHub stores code history. It does not automatically run the application or back up the ignored research data. Before accumulating valuable real research, establish a separate data backup. Later, move structured data into PostgreSQL, original documents and arrays into object storage, and execution onto a cloud worker. That migration needs implementation; it is not included in this starter.

## 2. Install the two prerequisites

These instructions assume Windows and VS Code desktop. You do not need Docker, a cloud account or an API key for this step.

1. Install Python from [python.org's Windows downloads](https://www.python.org/downloads/windows/). A standard 64-bit Python 3.13 installation is a reasonable starting choice; the setup code supports Python 3.11 or newer. Avoid the embeddable distribution for this project.
2. In VS Code, open Extensions with `Ctrl+Shift+X`, search for **Python**, and install the extension published by **Microsoft**. The editor extension and Python itself are separate installations.
3. Open **Terminal → New Terminal**. Use PowerShell for the commands below. Check:

```powershell
py --version
git --version
```

`py` should print Python 3.11 or newer. If Python was just installed, restart VS Code and try again. If `python --version` works but `py` does not, use `python` instead of `py` in the environment-creation command below.

If Git is missing, follow [VS Code's Git setup instructions](https://code.visualstudio.com/docs/sourcecontrol/overview) and restart VS Code. Signing into GitHub is separate from installing Git.

## 3. Put the project in one folder

Download and extract the ZIP. In File Explorer, move the extracted project folder to your usual coding location, for example your user folder's `Projects` directory. You may rename it to `probabilistic-dcf`.

In VS Code choose **File → Open Folder** and select the folder containing `pyproject.toml`, `README.md`, `configs/` and `src/`. Open the folder, not the ZIP and not only an individual Python file.

If you have already created an empty GitHub repository for this project, use `Ctrl+Shift+P` → **Git: Clone** to clone it first, then copy the extracted project's contents into that checkout. Do not overwrite an existing populated project. If you have only signed into GitHub, use the new-project route in step 7.

## 4. Create the project's Python environment

With the project folder open, choose **Terminal → New Terminal**. The terminal should be in the folder containing `pyproject.toml`. Run these commands one at a time:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m research_platform doctor
```

What each does:

| Command | Meaning |
|---|---|
| `py -m venv .venv` | Creates a private Python environment for this project |
| `python.exe -m pip install -e .` | Registers the code in that environment so it can be imported; `-e` means edits remain visible |
| `python.exe -m research_platform doctor` | Checks configuration and creates the local data/output directories |

The full `.venv` Python path deliberately avoids PowerShell activation-policy issues. No `Activate.ps1` or execution-policy change is required. The install may download build tools; the setup commands themselves make no external API calls.

Now press `Ctrl+Shift+P`, choose **Python: Select Interpreter**, and select the interpreter inside this project's `.venv`. If it is missing from the list, choose **Enter interpreter path** and select `.venv\Scripts\python.exe`.

## 5. Run the small FX demonstration

```powershell
.\.venv\Scripts\python.exe -m research_platform demo-fx
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The demonstration generates five synthetic currency scenarios, derives consistent cross rates, and applies the same scenario to two fictional companies with different reporting currencies. It saves CSVs and a manifest to a new folder under `outputs/`. Open the CSVs in Excel to inspect the numbers.

This only demonstrates shared inputs, currency conventions and reproducible exports. It is not a Nestlé model, a fitted FX forecasting process or the final Excel review interface. Its fictional exposures and arbitrary sampling ranges must never be used as company estimates. The production numerical model will use NumPy when we add large arrays; this small setup demo uses Python's standard library.

## 6. Understand the folders

| Path | What belongs here |
|---|---|
| `src/research_platform/data/` | Code for loading, validating and later persisting records |
| `src/research_platform/factors/` | Shared calculations such as FX and, later, commodity factors |
| `src/research_platform/models/` | Financial calculations; currently only the fictional translation example |
| `src/research_platform/reporting/` | Output writers; currently CSV and JSON, with Excel exports to add later |
| `src/research_platform/workflows/` | The order in which loading, calculations and saving happen |
| `configs/companies/` | Company identity and structural configuration; not a duplicate research database |
| `configs/shared_factors.json` | Shared topic definitions and conventions; not live forecasts |
| `tests/` | Small checks that protect numerical and operational behavior |
| `docs/` | Architecture and the next build steps |
| `local_store/` | Local research data; created by `doctor`, ignored by Git |
| `outputs/` | Saved runs and exports; ignored by Git |
| `.venv/` | Installed Python environment; ignored by Git |
| `pyproject.toml` | Project metadata and, later, dependency declarations |
| `.gitignore` | Tells Git which generated/private files to exclude |
| `.env.example` | Example future configuration names; no credentials |
| `AGENTS.md` | Instructions for coding assistants, including challenging drift from the investment vision |

We will extend `models/` with Nestlé's financial equations, put large-scale assumption sampling in a dedicated module, and extend `reporting/` with Excel exports. Avoid creating many empty services now.

The folder called `data` inside `src` contains **code that handles data**. `local_store` contains **the data itself**. That distinction lets us change storage without rewriting the financial equations.

## 7. Save the code in GitHub

If this is a new project, open the Source Control view (`Ctrl+Shift+G`) and select **Initialize Repository**. Review the listed files; `.venv/`, `local_store/`, `outputs/` and `.env` should not appear. Stage the project files, enter `Initial research platform setup`, and commit. If Git asks for your name/email, provide the identity you want attached to your commits.

Use **Publish to GitHub**, select **Private**, and choose a repository name such as `probabilistic-dcf`. If you cloned an existing repository, commit and use **Sync Changes** or **Push** instead of creating another repository. Review the files before each commit. A private repository is still not a place for API keys or restricted source datasets.

All companies should initially share this one repository. Company configuration differs; shared financial functions, research infrastructure and FX calculations are reused.

## 8. Your everyday workflow

Open this project folder in VS Code, edit files, run the checks relevant to the change, review the results, then commit and push code changes. The virtual environment does not need recreating each time. Re-run `pip install -e .` when package metadata or dependencies change.

When we add new dependencies, record and pin the approved environment before research runs that need reproducibility. Saving only a random seed is insufficient: preserve actual input versions, generated samples, code version and package versions too.

| Problem | First check |
|---|---|
| `py` is not recognized | Restart VS Code after Python installation; try `python --version` |
| `.venv\Scripts\python.exe` cannot be found | Check you opened the correct folder and created `.venv` there |
| No `pyproject.toml` / project not found | Open the extracted project folder, rather than its parent |
| `No module named research_platform` | Re-run the editable install using this project's `.venv` Python |
| Permission or network error during installation | Read the first error; do not change system security settings blindly |
| No GitHub repository visible | Check whether you have only signed in, or actually cloned/published a repository |

For macOS/Linux, use `python3 -m venv .venv`, then `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.

Next read [the architecture](docs/architecture.md) and [the first build milestones](docs/next_steps.md). Today's completion point is that `doctor` succeeds, the synthetic example runs, and you can inspect the project files. Live data ingestion and the Nestlé financial model come next.

## Official setup references

- [Python in VS Code](https://code.visualstudio.com/docs/python/python-tutorial)
- [Selecting a Python environment](https://code.visualstudio.com/docs/python/environments)
- [Python virtual environments](https://docs.python.org/3.13/library/venv.html)
- [Editable Python installs](https://setuptools.pypa.io/en/latest/userguide/development_mode.html)
- [VS Code repositories and remotes](https://code.visualstudio.com/docs/sourcecontrol/repos-remotes)

Technical guidance checked on 10 October 2026. Runtime checks were executed in the provided Linux Python environment; Windows desktop installation was not executed here.
