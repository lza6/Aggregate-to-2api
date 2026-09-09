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
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

const BACKEND_ADDR: &str = "127.0.0.1:8100";
const HEALTH_PATH: &str = "/v1/healthz";

struct BackendState {
    uvicorn_pid: Option<u32>,
    solver_pid: Option<u32>,
}

fn state() -> &'static Mutex<BackendState> {
    static STATE: OnceLock<Mutex<BackendState>> = OnceLock::new();
    STATE.get_or_init(|| {
        Mutex::new(BackendState {
            uvicorn_pid: None,
            solver_pid: None,
        })
    })
}

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

    let use_sidecar = !std::env::var("IF_DESKTOP_USE_PYINSTALLER").is_ok() || env_yes("IF_DESKTOP_USE_PYINSTALLER");
    // python 解析为 owned String（供 Command::new 长期持有）
    let python: String;
    let args: Vec<String> = if use_sidecar {
        // sidecar 模式：exe 目录附近 backend/uvicorn.exe（PyInstaller 单文件，自足）。
        // 开发时位于 src-tauri/target/release，上溯找 backend/；安装版在程序目录直接有。
        python = {
            let mut cwd = std::env::current_dir().unwrap_or_default();
            let mut found = "backend/uvicorn.exe".to_string();
            for _ in 0..6 {
                let cand = cwd.join("backend").join("uvicorn.exe");
                if cand.exists() {
                    found = cand.to_string_lossy().into_owned();
                    break;
                }
                if !cwd.pop() {
                    break;
                }
            }
            found
        };
        vec![]
    } else {
        // 系统 PATH 可能没有 `python`（仅 .venv 存在）。优先：
        // 1) IF_DESKTOP_PYTHON 显式指定可执行文件
        // 2) 上溯 cwd 找仓库根 .venv/Scripts/python.exe
        // 3) 兜底 `python`（能解析成功即可）
        python = std::env::var("IF_DESKTOP_PYTHON").ok().filter(|s| !s.is_empty()).unwrap_or_else(|| {
            let mut cwd = std::env::current_dir().unwrap_or_default();
            loop {
                let venv = cwd.join(".venv").join("Scripts").join("python.exe");
                if venv.exists() {
                    break venv.to_string_lossy().into_owned();
                }
                if !cwd.pop() {
                    break "python".into();
                }
            }
        });
        vec!["-m".into(), "uvicorn".into(), "api.main:app".into(), "--host".into(), "127.0.0.1".into(), "--port".into(), "8100".into()]
    };

    // 后端以项目根为工作目录：Tauri 子进程默认 cwd = exe 所在目录，
    // 相对导入 `api.main:app` 必须从仓库根解析。开发目录存在时回退该根；
    // 打包安装版（无源码根）依赖 sidecar（backend/uvicorn.exe 自带 api 资源）。
    let mut project_root: Option<std::path::PathBuf> = std::env::var("IF_DESKTOP_PROJECT_ROOT")
        .ok()
        .filter(|s| !s.is_empty())
        .map(std::path::PathBuf::from);

    // 未显式指定时，上溯 cwd 找含 api/main.py 的仓库根
    if project_root.is_none() {
        let mut cwd = std::env::current_dir().unwrap_or_default();
        for _ in 0..6 {
            if cwd.join("api").join("main.py").exists() {
                project_root = Some(cwd);
                break;
            }
            if !cwd.pop() {
                break;
            }
        }
    }

    let mut cmd = Command::new(&python);
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
    if let Some(root) = project_root {
        cmd.current_dir(root);
    }

    let child = cmd.spawn().ok()?;
    Some(child.id())
}

fn spawn_solver() -> Option<u32> {
    use std::process::{Command, Stdio};
    // 与 spawn_uvicorn 同策略：上溯找 .venv 的 python，找不到回退 `python`
    let python = std::env::var("IF_DESKTOP_PYTHON").ok().filter(|s| !s.is_empty()).unwrap_or_else(|| {
        let mut cwd = std::env::current_dir().unwrap_or_default();
        loop {
            let venv = cwd.join(".venv").join("Scripts").join("python.exe");
            if venv.exists() {
                break venv.to_string_lossy().into_owned();
            }
            if !cwd.pop() {
                break "python".into();
            }
        }
    });
    // 仅当仓库根存在 boterdrop_wrapper.py 才拉 solver（cwd 未切到仓库根时跳过）
    let mut root = std::env::var("IF_DESKTOP_PROJECT_ROOT").ok().map(std::path::PathBuf::from);
    if root.is_none() {
        let mut cwd = std::env::current_dir().unwrap_or_default();
        for _ in 0..6 {
            if cwd.join("deploy").join("cf_solver").join("boterdrop_wrapper.py").exists() {
                root = Some(cwd);
                break;
            }
            if !cwd.pop() {
                break;
            }
        }
    }
    let wrapper = root.as_ref()?.join("deploy").join("cf_solver").join("boterdrop_wrapper.py");
    if !wrapper.exists() {
        return None;
    }
    let mut cmd = Command::new(&python);
    cmd.arg(&wrapper).stdout(Stdio::null()).stderr(Stdio::null());
    if let Some(r) = root {
        cmd.current_dir(r);
    }
    let child = cmd.spawn().ok()?;
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
    let st = state().lock().unwrap();
    BackendStatus {
        ready: backend_ready(),
        backend_pid: st.uvicorn_pid,
        solver_pid: st.solver_pid,
        detail: String::new(),
    }
}

pub fn run() {
    use tauri::Manager;
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            {
                let mut st = state().lock().unwrap();
                st.uvicorn_pid = spawn_uvicorn();
                if !env_yes("IF_DESKTOP_NO_SOLVER") {
                    st.solver_pid = spawn_solver();
                }
            }

            // 健康探测后台线程：就绪后显示主窗口（60s 超时兜底）
            // 注意：闭包内 move 捕获 handle，不能在外层再次 move 进嵌套闭包——
            // run_on_main_thread 闭包需 clone 一份 handle。
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let deadline = std::time::Instant::now() + Duration::from_secs(60);
                while std::time::Instant::now() < deadline {
                    if backend_ready() {
                        let h = handle.clone();
                        let _ = handle.run_on_main_thread(move || {
                            if let Some(win) = h.get_webview_window("main") {
                                let _ = win.show();
                                let _ = win.set_focus();
                            }
                        });
                        return;
                    }
                    std::thread::sleep(Duration::from_millis(600));
                }
                // 超时仍显示（后端可能失败，UI 会显示 backend_status）
                let h = handle.clone();
                let _ = handle.run_on_main_thread(move || {
                    if let Some(win) = h.get_webview_window("main") {
                        let _ = win.show();
                    }
                });
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                // 主窗口关闭 → 终止后端子进程（防孤儿）
                let st = state().lock().unwrap();
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
