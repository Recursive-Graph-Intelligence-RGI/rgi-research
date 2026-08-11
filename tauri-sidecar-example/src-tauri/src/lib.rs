mod governance;

use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use governance::Governance;
use serde::{Deserialize, Serialize};
use tauri::State;

struct RGIState {
    child: Mutex<Option<Child>>,
    port: Mutex<u16>,
    governance: Mutex<Governance>,
}

#[derive(Serialize)]
struct StartResult {
    port: u16,
    pid: Option<u32>,
}

#[derive(Serialize, Deserialize, Debug)]
struct JobStatus {
    id: String,
    status: String,
    progress: Vec<String>,
    error: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
struct JobResult {
    id: String,
    status: String,
    result: Option<serde_json::Value>,
    error: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
struct AnalyzeResponse {
    job_id: String,
    status: String,
}

fn python_executable() -> String {
    std::env::var("RGI_PYTHON_PATH").unwrap_or_else(|_| "python".to_string())
}

fn default_allowed_root() -> PathBuf {
    // Default hard boundary: the user's home directory. In a real product this
    // would be configurable at install time or per-workspace.
    dirs::home_dir().unwrap_or_else(|| PathBuf::from("/"))
}

fn find_free_port() -> u16 {
    // Let the OS assign a free port by binding a temporary socket.
    let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind failed");
    let port = listener.local_addr().unwrap().port();
    drop(listener);
    port
}

fn wait_for_health(port: u16) -> Result<(), String> {
    let url = format!("http://127.0.0.1:{}/health", port);
    for _ in 0..60 {
        if let Ok(response) = ureq::get(&url).timeout(Duration::from_secs(1)).call() {
            if response.status() == 200 {
                return Ok(());
            }
        }
        thread::sleep(Duration::from_millis(250));
    }
    Err("RGI engine did not become healthy".to_string())
}

fn rgi_url(state: &RGIState, path: &str) -> String {
    let port = *state.port.lock().unwrap();
    format!("http://127.0.0.1:{}{}", port, path)
}

#[tauri::command]
fn start_rgi(state: State<RGIState>) -> Result<StartResult, String> {
    let mut child_guard = state.child.lock().unwrap();
    if child_guard.is_some() {
        return Err("RGI engine is already running".to_string());
    }

    let port = find_free_port();
    let python = python_executable();
    let governance = state.governance.lock().unwrap().clone();

    let mut cmd = Command::new(&python);
    cmd.arg("-m")
        .arg("rgi")
        .arg("server")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string());

    governance.apply_to(&mut cmd);

    let child = cmd
        .spawn()
        .map_err(|e| format!("failed to spawn RGI engine: {}", e))?;

    wait_for_health(port)?;

    let pid = child.id();
    *child_guard = Some(child);
    *state.port.lock().unwrap() = port;

    Ok(StartResult { port, pid: Some(pid) })
}

#[tauri::command]
fn stop_rgi(state: State<RGIState>) -> Result<(), String> {
    let mut child_guard = state.child.lock().unwrap();
    if let Some(mut child) = child_guard.take() {
        // Try graceful shutdown via HTTP first.
        let url = rgi_url(&state, "/shutdown");
        let _ = ureq::post(&url).timeout(Duration::from_secs(2)).call();
        thread::sleep(Duration::from_millis(500));

        let _ = child.kill();
        let _ = child.wait();
    }
    Ok(())
}

#[tauri::command]
fn analyze_repo(state: State<RGIState>, path: String, objective: String) -> Result<String, String> {
    let target = PathBuf::from(&path);
    let governance = state.governance.lock().unwrap().clone();
    if !governance.path_allowed(&target) {
        return Err(format!(
            "path {} is outside the allowed workspace {:?}",
            path, governance.allowed_root
        ));
    }

    let url = rgi_url(&state, "/analyze");
    let body = serde_json::json!({
        "path": path,
        "objective": objective,
        "mock": true,
    });

    let response = ureq::post(&url)
        .send_json(&body)
        .map_err(|e| format!("analyze request failed: {}", e))?;

    let data: AnalyzeResponse = response
        .into_json()
        .map_err(|e| format!("failed to parse analyze response: {}", e))?;

    Ok(data.job_id)
}

#[tauri::command]
fn get_status(state: State<RGIState>, job_id: String) -> Result<JobStatus, String> {
    let url = rgi_url(&state, &format!("/jobs/{}/status", job_id));
    let response = ureq::get(&url)
        .call()
        .map_err(|e| format!("status request failed: {}", e))?;

    response
        .into_json()
        .map_err(|e| format!("failed to parse status response: {}", e))
}

#[tauri::command]
fn get_result(state: State<RGIState>, job_id: String) -> Result<JobResult, String> {
    let url = rgi_url(&state, &format!("/jobs/{}/result", job_id));
    let response = ureq::get(&url)
        .call()
        .map_err(|e| format!("result request failed: {}", e))?;

    response
        .into_json()
        .map_err(|e| format!("failed to parse result response: {}", e))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let allowed_root = default_allowed_root();
    let governance = Governance::new(&allowed_root);

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(RGIState {
            child: Mutex::new(None),
            port: Mutex::new(8787),
            governance: Mutex::new(governance),
        })
        .invoke_handler(tauri::generate_handler![
            start_rgi,
            stop_rgi,
            analyze_repo,
            get_status,
            get_result,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
