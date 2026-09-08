// 听风AI 桌面版 —— Rust 主进程（Tauri 2.x）核心实现。
//
// 方案：Tauri sidecar 托管 Python 后端。
//  - 应用启动：拉取本地 uvicorn（127.0.0.1:8100）+ 可选的 cf_solver（8001）
//  - 健康探测：轮询 /v1/healthz 就绪后才显示主窗口（避免白屏）
//  - 窗口关闭：按 pid 终止后端子进程，不留孤儿
//  - 命令 `backend_status` 暴露给前端（UI 展示「后端启动中/就绪」）
//
// 说明：本机无 cargo/rustc，此文件为**可编译的标准 Tauri 2 脚手架**，
// 需安装 rustup + `cargo install tauri-cli` 后 `cargo build` 验证（见 README 构建章节）。
// 仅 Windows 目标；UI 用系统 WebView2。

use serde::Serialize;
use std::sync::Mutex;
use std::time::Duration;

const BACKEND_ADDR: &str = "127.0.0.1:8100";
const HEALTH_PATH: &str = "/v1/healthz";

struct BackendState {
    uvicorn_pid: Option<u32>,
    solver_pid: Option<u32>,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            uvicorn_pid: None,
            solver_pid: None,
        }
    }
}

static STATE: Mutex<BackendState> = Mutex::new(BackendState::default());

#[derive(Serialize, Clone)]
struct BackendStatus {
    ready: bool,
    backend_pid: Option<u32>,
    solver_pid: Option<u32>,
    detail: String,
}

fn env_yes(name: &str) -> bool {
    std::env::var(name)
        .map(|v| matches!(v.trim().to_lowercase().as_str(), "1" | "true" | "yes" | "on"))
        .unwrap_or(false)
}

/// 启动后端进程（uvicorn）。优先用 PyInstaller 打包的 sidecar，
/// 未找到时回退系统 `python -m uvicorn api.main:app`。
fn spawn_uvicorn() -> Option<u32> {
    use std::process::{Command, Stdio};

    let use_sidecar = env_yes("IF_DESKTOP_USE_PYINSTALLER");
    let (exe, args) = if use_sidecar {
        ("backend/uvicorn.exe", vec![])
    } else {
        (
            "python",
            vec!["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8100"],
        )
    };

    let mut cmd = Command::new(exe);
    cmd.args(&args)
        .env("IF_HOST", "127.0.0.1")
        .env("IF_PORT", "8100")
        .env("IF_CF_SOLVER_URL", "http://127.0.0.1:8001")
        .env(
            "IF_MOCK_UPSTREAM",
            if env_yes("IF_DESKTOP_MOCK_UPSTREAM") { "1" } else { "0" },
        )
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    let child = cmd.spawn().ok()?;
    Some(child.id())
}

fn spawn_solver() -> Option<u32> {
    use std::process::{Command, Stdio};
    let child = Command::new("python")
        .args(["deploy/cf_solver/boterdrop_wrapper.py"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;
    Some(child.id())
}

#[cfg(windows)]
fn kill_pid(pid: u32) {
    unsafe {
        use windows::Win32::Foundation::CloseHandle;
        use windows::Win32::System::Threading::{OpenProcess, TerminateProcess, PROCESS_TERMINATE};
        if let Ok(handle) = OpenProcess(PROCESS_TERMINATE, false, pid) {
            let _ = TerminateProcess(handle, 1);
            let _ = CloseHandle(handle);
        }
    }
}

#[cfg(not(windows))]
fn kill_pid(pid: u32) {
    let _ = std::process::Command::new("kill").arg(pid.to_string()).status();
}

/// 极简 HTTP GET（标准库 TcpStream），返回 200 且 body 含 ok/degraded 视为就绪。
fn backend_ready() -> bool {
    use std::io::{Read, Write};
    use std::net::TcpStream;

    let Ok(mut stream) = TcpStream::connect_timeout(
        &(BACKEND_ADDR).parse().unwrap(),
        Duration::from_millis(800),
    ) else {
        return false;
    };
    let req = format!(
        "GET {HEALTH_PATH} HTTP/1.1\r\nHost: {BACKEND_ADDR}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 1024];
    let mut body = String::new();
    loop {
        match stream.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => body.push_str(&String::from_utf8_lossy(&buf[..n])),
            Err(_) => return false,
        }
    }
    body.starts_with("HTTP/1.1 200") && (body.contains("\"ok\"") || body.contains("\"degraded\""))
}

#[tauri::command]
fn backend_status() -> BackendStatus {
    let st = STATE.lock().unwrap();
    BackendStatus {
        ready: backend_ready(),
        backend_pid: st.uvicorn_pid,
        solver_pid: st.solver_pid,
        detail: String::new(),
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            {
                let mut st = STATE.lock().unwrap();
                st.uvicorn_pid = spawn_uvicorn();
                if !env_yes("IF_DESKTOP_NO_SOLVER") {
                    st.solver_pid = spawn_solver();
                }
            }

            // 健康探测后台线程：就绪后显示主窗口（60s 超时兜底）
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let deadline = std::time::Instant::now() + Duration::from_secs(60);
                while std::time::Instant::now() < deadline {
                    if backend_ready() {
                        let _ = handle.run_on_main_thread(move || {
                            if let Some(win) = handle.get_webview_window("main") {
                                let _ = win.show();
                                let _ = win.set_focus();
                            }
                        });
                        return;
                    }
                    std::thread::sleep(Duration::from_millis(600));
                }
                // 超时仍显示（后端可能失败，UI 会显示 backend_status）
                let _ = handle.run_on_main_thread(move || {
                    if let Some(win) = handle.get_webview_window("main") {
                        let _ = win.show();
                    }
                });
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                // 主窗口关闭 → 终止后端子进程（防孤儿）
                let st = STATE.lock().unwrap();
                if let Some(p) = st.uvicorn_pid {
                    kill_pid(p);
                }
                if let Some(p) = st.solver_pid {
                    kill_pid(p);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![backend_status])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
