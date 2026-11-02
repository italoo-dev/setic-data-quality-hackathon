# AI Agent Governance & Workflow Guidelines (AGENTS.md)

This document establishes the governance, architectural, and development rules for AI coding agents (and human engineers) working on the **SETIC Centralized Data Quality, Normalization, and Governance Platform** (State Secretariat of Information and Communication Technology of Rondônia - Challenge 1 / CAGD).

---

## 1. System Context & Mission

The platform operates as a centralized gatekeeper that intercepts incoming administrative data before persistence into state government databases.
Its primary responsibility rests upon two non-negotiable architectural principles:

1. **Permissive Normalization**:
   - Conceptually valid data provided in arbitrary, informal, unmasked, or truncated formats must be sanitized and converted into standardized canonical standards.
   - *Examples*:
     - Natural language Portuguese dates (`"15 de março de 1985"` or `"15/03/85"`) $\rightarrow$ Canonical ISO-8601 (`"1985-03-15"`).
     - Informal or abbreviated municipalities (`"p. velho"`, `"jiparana"`, `"sao paulo"`) $\rightarrow$ Official IBGE name (`"Porto Velho"`, `"Ji-Paraná"`, `"São Paulo"`), official 7-digit IBGE code (`"1100205"`), and state abbreviation (`"RO"`).
     - Unmasked or inconsistently punctuated documents (`"12345678901"` or `"123.456.789-01"`) $\rightarrow$ Sanitized canonical digits.
     - Telephones and Postal Codes (CEP) with or without delimiters $\rightarrow$ Canonical national format.

2. **Strict Blocking**:
   - Data containing irrecoverable structural, mathematical, or semantic flaws must be **strictly blocked**, preventing persistence.
   - The API response must strictly return **`HTTP 422 Unprocessable Entity`** with a detailed field-level diagnostic report (`campo`, `regra_violada`, `valor_rejeitado`, `formato_esperado`, `mensagem`).
   - Every submission attempt (whether accepted or rejected) must be recorded for CAGD telemetry and operational auditing.
   - *Examples of Rejection*:
     - Checksum verification failure on CPF or CNPJ.
     - Calendar impossibilities (e.g. `31/02/1990`, `29/02/2023`, `31/04/2021`).
     - Non-existent municipalities or states in the national IBGE registry.
     - Violation of active dynamic business rules (e.g. employee registration number format).

---

## 2. Atomic Commit Standards (Conventional Commits)

Development agents must strictly adhere to **Atomic and Isolated Commits**. Never create monolithic commits ("git dumps") that combine multiple distinct application layers.

When making closely related modifications, formatting fixes, or refinements belonging to the same logical unit/layer, **prefer amending the previous commit (`git commit --amend`)** rather than fragmenting history into multiple scattered micro-commits. Always preserve **atomicity** and conceptual cohesion across each architectural layer.

**Agents must never execute `git push`**: all commits, amends, and rebases must remain strictly local on the working branch. Pushing to remote repositories (`origin`) is exclusively reserved for the human developer.

Each commit must represent a single architectural layer or independent logical unit:

| Type | Scope | Commit Description |
| :--- | :--- | :--- |
| `docs` | `(agents)` | Updates to governance rules, agent guidelines, and contracts. |
| `feat` | `(packaging)` | Declarative packaging and dependency configuration (`pyproject.toml`). |
| `feat` | `(nix)` | Reproducible environment, derivations, and devshell (`flake.nix`). |
| `feat` | `(infra)` | Docker / Podman container configurations (`docker-compose.yml`). |
| `feat` | `(database)` | Persistence layer, SQLAlchemy models, and database sessions. |
| `feat` | `(validators)` | Canonical immutable validators for CPF, CNPJ, IBGE, dates, etc. |
| `feat` | `(engine)` | Hybrid validation pipeline engine (core rules + dynamic rules). |
| `feat` | `(schemas)` | Pydantic V2 models for input, normalized output, and diagnostics. |
| `feat` | `(api)` | FastAPI REST routes, dependencies, and telemetry. |
| `feat` | `(dashboard)` | CAGD Streamlit management dashboard (metrics, rules, sandbox). |
| `docs` | `(readme)` | Architectural documentation, setup instructions, and curl examples. |
| `test` | `(core)` | Automated unit and integration test suite. |
| `refactor` | `(core)` | Structural code cleanup and pattern refactoring. |

---

## 3. Single Source of Truth for Dependencies

1. **`pyproject.toml` is the sole source of truth** for project metadata, runtime dependencies, development tools, and linter/LSP configurations (PEP 621).
2. **Never declare static Python package lists in `flake.nix`**.
3. `flake.nix` must dynamically read and parse `pyproject.toml` (via `pyproject.nix`, `uv2nix`, or `builtins.fromTOML`), guaranteeing zero synchronization drift.
4. LSPs (Pyright, Ruff) must read configurations directly from `pyproject.toml`.

---

## 4. Non-Negotiable Architectural Safeguards

1. **Use Certified National Libraries**:
   - Never write custom regex algorithms for CPF/CNPJ when `brutils` is available.
   - The official catalogue of all 5,570+ Brazilian municipalities must resolve locally from `brutils` (`brutils/data/cities_code.json`). External network requests during validation are strictly prohibited; the engine operates 100% offline with maximum determinism and low latency.
   - Phone and DDD validation must utilize `phonenumbers` (Google libphonenumber), eliminating manual operator or area code mapping tables.
   - Approximate and informal spelling variations must resolve via `RapidFuzz` and `Unidecode`.
2. **Core Rule Immutability**:
   - Core structural rules (CPF, CNPJ, Birth Date, Phone, IBGE Municipality/UF) are foundational and must remain marked immutable (`eh_imutavel = True`).
   - The management interface (Streamlit) and API endpoints must forbid editing or deleting immutable rules.
3. **Reliable Persistence & Telemetry**:
   - Corrupted or rejected payloads must **never** be stored in validated production tables.
   - Every invocation of `/api/v1/validar` must generate a `RegistroAuditoria` log recording protocol, input payload, status (success/failure), latency in milliseconds, and error diagnostics.
4. **Localization & Language**:
   - All API documentation (OpenAPI / Swagger), error diagnostic messages, Pydantic schemas, user interfaces, and domain models must be written in **formal Brazilian Portuguese (pt-BR)**.
5. **Strict Prohibition of Retrocompatibility Shims**:
   - Never create or retain backward-compatibility adapters, property wrappers, aliases, or deprecated shims when refactoring or renaming symbols (classes, functions, methods, parameters, or attributes).
   - When renaming or modifying contracts, obsolete implementations must be deleted completely, and all call sites/tests must be updated directly.
   - Zero tolerance for legacy cruft; the codebase must remain lean, canonical, and strictly typed.

---

## 5. Pre-Commit Verification Loop

Code integrity and zero-regression guarantees are enforced through multiple mandatory layers before any commit or submission:

1. **Declarative Git Pre-Commit Hooks** (`git-hooks.nix` in `flake.nix`):
   - Automatically intercept commits to execute `ruff`, `ruff-format`, `trim-trailing-whitespace`, and `end-of-file-fixer`.
   - Validate manually via `pre-commit run --all-files` or `nix flake check`.

2. **Static Type Checking & Zero `Any`**:
   - `pyright` must report 0 errors and 0 warnings.
   - `git grep -n "\bAny\b" backend/ frontend/` must return 0 occurrences.

3. **Automated Test Suite**:
   - `pytest` must pass 100% of unit and integration tests (`backend/tests`, `frontend/tests`).

4. **Mandatory Runtime Sanity Check & Build**:
   - **Never submit changes based solely on linters or static type checks** without verifying that the system **actually boots and runs without runtime errors** (`ModuleNotFoundError`, `ImportError`, injection issues, or lifecycle crashes).
   - **Package Build**: Run `nix build` to confirm package derivations build cleanly.
   - **FastAPI Startup Smoke Test**: Verify that the API starts and responds on `/api/v1/saude` with HTTP 200.
   - **Streamlit Startup Smoke Test**: Verify that the dashboard runs without exceptions (`streamlit run frontend/app.py --server.headless true`).

```bash
# 1. Run git pre-commit hooks on all files
pre-commit run --all-files

# 2. Static type check (zero errors, zero Any)
pyright
git grep -n "\bAny\b" backend/ frontend/

# 3. Automated test suite (unit and integration)
pytest backend/tests frontend/tests -v

# 4. Nix build verification & runtime smoke test
nix build
python -c "from backend.main import app; print('Runtime OK')"
```

Any syntax error, typing defect, contract violation, or runtime failure must be completely resolved before committing.

---

## 6. Remote Repository Operations (Strict Prohibition of Git Push)

Coding agents must **never execute `git push` under any circumstances** (including `--force`, `--force-with-lease`, or standard push).
- All work, verification passes, and atomic commits must remain exclusively local on the machine.
- Pushing commits or tags to the remote repository (`origin`) is an action reserved exclusively for the human engineer.
- Never trigger automated pushes or remote branch updates.
