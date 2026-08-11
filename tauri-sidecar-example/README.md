# RGI Tauri Sidecar Example

A minimal Tauri desktop app that spawns the RGI Python engine as a local HTTP service and drives it from a TypeScript/Vite frontend.

This example lives in the RGI repo to demonstrate the integration pattern for `rlmlocal-site` without modifying that project.

## Prerequisites

- Rust + cargo
- Node.js + npm
- Python 3.12+ with the RGI package installed (`pip install -e ..` from the repo root)
- `cargo-tauri` installed (`cargo install tauri-cli`)

## Run in development

```bash
cd tauri-sidecar-example
npm install
npm run tauri:dev
```

The app will:
1. Spawn `python -m rgi server --port 8787` in the background.
2. Wait for the `/health` endpoint.
3. Let you pick a folder, enter an objective, and run an analysis.
4. Poll status and display the final report.

## Build

```bash
npm run tauri:build
```

Produces a native desktop binary in `src-tauri/target/release/bundle/`.

## Architecture

```
Tauri desktop app
├── Webview (TS/Vite)  → user interface
├── Rust host          → process management + HTTP bridge
│   └── spawns RGI Python engine on localhost
└── RGI Python engine  → recursive graph intelligence
```

## Notes

- This example assumes RGI is installed in the same Python environment that `python` resolves to.
- In a real product, the Python runtime and RGI package would be bundled with the Tauri installer.
- FortSignal governance is not implemented in this example; see Milestones 3 and 4 of the v0.3 plan.
