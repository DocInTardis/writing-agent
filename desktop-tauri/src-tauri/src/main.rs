use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

#[cfg(windows)]
use std::os::windows::io::AsRawHandle;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
use windows::Win32::Foundation::{CloseHandle, HANDLE};
#[cfg(windows)]
use windows::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};

const APP_TITLE: &str = "写作助手";
const BASE_PORT: u16 = 8765;
const PORT_TRIES: u16 = 40;

#[cfg(windows)]
struct WindowsJob(HANDLE);

#[cfg(windows)]
unsafe impl Send for WindowsJob {}
#[cfg(windows)]
unsafe impl Sync for WindowsJob {}

#[cfg(windows)]
impl WindowsJob {
    fn attach(child: &Child) -> Result<Self, String> {
        unsafe {
            let job =
                CreateJobObjectW(None, None).map_err(|err| format!("创建进程组失败: {err}"))?;
            let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if let Err(err) = SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const std::ffi::c_void,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            ) {
                let _ = CloseHandle(job);
                return Err(format!("配置进程组失败: {err}"));
            }
            let process = HANDLE(child.as_raw_handle());
            if let Err(err) = AssignProcessToJobObject(job, process) {
                let _ = CloseHandle(job);
                return Err(format!("绑定内置服务进程失败: {err}"));
            }
            Ok(Self(job))
        }
    }
}

#[cfg(windows)]
impl Drop for WindowsJob {
    fn drop(&mut self) {
        unsafe {
            let _ = CloseHandle(self.0);
        }
    }
}

struct BackendProcess {
    child: Child,
    #[cfg(windows)]
    _job: WindowsJob,
}

struct BackendState(Mutex<Option<BackendProcess>>);

impl BackendState {
    fn stop(&self) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(mut backend) = guard.take() {
                let _ = backend.child.kill();
                let _ = backend.child.wait();
            }
        }
    }
}

impl Drop for BackendState {
    fn drop(&mut self) {
        if let Ok(slot) = self.0.get_mut() {
            if let Some(backend) = slot.as_mut() {
                let _ = backend.child.kill();
                let _ = backend.child.wait();
            }
        }
    }
}

fn project_root() -> Result<PathBuf, String> {
    if let Some(value) = std::env::var_os("WRITING_AGENT_PROJECT_ROOT") {
        return Ok(PathBuf::from(value));
    }
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| "无法定位项目目录".to_string())
}

fn choose_port() -> Result<u16, String> {
    for port in BASE_PORT..BASE_PORT.saturating_add(PORT_TRIES) {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return Ok(port);
        }
    }
    Err(format!(
        "本地端口 {}..{} 均被占用",
        BASE_PORT,
        BASE_PORT + PORT_TRIES - 1
    ))
}

fn packaged_sidecar(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    app.path()
        .resource_dir()
        .map(|path| {
            path.join("sidecar")
                .join("writing-agent-sidecar")
                .join("writing-agent-sidecar.exe")
        })
        .map_err(|err| format!("无法定位内置服务: {err}"))
}

fn development_python(root: &Path) -> Option<PathBuf> {
    let configured = std::env::var_os("WRITING_AGENT_PYTHON").map(PathBuf::from);
    let windows = root.join(".venv").join("Scripts").join("python.exe");
    let unix = root.join(".venv").join("bin").join("python");
    configured
        .or_else(|| windows.exists().then_some(windows))
        .or_else(|| unix.exists().then_some(unix))
}

fn start_backend(app: &tauri::AppHandle, port: u16) -> Result<BackendProcess, String> {
    let root = project_root()?;
    let legacy_data = root.join(".data");
    let mut command = if cfg!(debug_assertions) {
        let python = development_python(&root).ok_or_else(|| {
            "未找到 .venv 中的 Python；请先运行 scripts/start_desktop.ps1".to_string()
        })?;
        let mut cmd = Command::new(python);
        cmd.args([
            "-B",
            "-m",
            "writing_agent.sidecar",
            "--host",
            "127.0.0.1",
            "--port",
            &port.to_string(),
        ]);
        cmd.current_dir(&root);
        cmd
    } else {
        let executable = packaged_sidecar(app)?;
        if !executable.is_file() {
            return Err(format!("安装包缺少内置服务: {}", executable.display()));
        }
        let mut cmd = Command::new(executable);
        cmd.args(["--host", "127.0.0.1", "--port", &port.to_string()]);
        cmd
    };
    if std::env::var_os("WRITING_AGENT_LEGACY_DATA_DIR").is_none() && legacy_data.is_dir() {
        command.env("WRITING_AGENT_LEGACY_DATA_DIR", legacy_data);
    }
    #[cfg(windows)]
    command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    let mut child = command
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("WRITING_AGENT_DESKTOP", "1")
        .env("WRITING_AGENT_PERF_MODE", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|err| format!("启动内置服务失败: {err}"))?;
    #[cfg(windows)]
    let job = match WindowsJob::attach(&child) {
        Ok(job) => job,
        Err(err) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(err);
        }
    };
    Ok(BackendProcess {
        child,
        #[cfg(windows)]
        _job: job,
    })
}

fn wait_until_ready(
    backend: &mut BackendProcess,
    address: SocketAddr,
    timeout: Duration,
) -> Result<(), String> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if let Some(status) = backend
            .child
            .try_wait()
            .map_err(|err| format!("检查内置服务失败: {err}"))?
        {
            return Err(format!("内置服务提前退出（{status}）"));
        }
        if TcpStream::connect_timeout(&address, Duration::from_millis(150)).is_ok() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(80));
    }
    Err("内置服务启动超过 30 秒".to_string())
}

fn create_main_window(app: &tauri::AppHandle, port: u16) -> Result<(), String> {
    let url = format!("http://127.0.0.1:{port}/")
        .parse()
        .map_err(|err| format!("无效的本地地址: {err}"))?;
    let mut builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
        .title(APP_TITLE)
        .inner_size(1440.0, 900.0)
        .min_inner_size(960.0, 640.0)
        .resizable(true)
        .incognito(true)
        .on_download(|_, _| true);

    if let Ok(cache_root) = app.path().app_cache_dir() {
        builder = builder.data_directory(cache_root.join("webview"));
    }
    builder
        .build()
        .map(|_| ())
        .map_err(|err| format!("创建主窗口失败: {err}"))
}

fn show_startup_error(app: &tauri::AppHandle, message: &str) {
    let escaped = message
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;");
    let html = format!(
        "data:text/html;charset=utf-8,<meta charset='utf-8'><title>启动失败</title><body style='font-family:Segoe UI,Microsoft YaHei,sans-serif;padding:32px'><h2>写作助手启动失败</h2><p>{escaped}</p></body>"
    );
    if let Ok(url) = url::Url::parse(&html) {
        let _ = WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
            .title("写作助手 - 启动失败")
            .inner_size(720.0, 420.0)
            .build();
    }
}

fn main() {
    tauri::Builder::default()
        .manage(BackendState(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            let port = match choose_port() {
                Ok(port) => port,
                Err(err) => {
                    show_startup_error(&handle, &err);
                    return Ok(());
                }
            };
            match start_backend(&handle, port) {
                Ok(mut backend) => {
                    let address = SocketAddr::from(([127, 0, 0, 1], port));
                    match wait_until_ready(&mut backend, address, Duration::from_secs(30)) {
                        Ok(()) => {
                            *handle.state::<BackendState>().inner().0.lock().unwrap() =
                                Some(backend);
                            if let Err(err) = create_main_window(&handle, port) {
                                handle.state::<BackendState>().stop();
                                show_startup_error(&handle, &err);
                            }
                        }
                        Err(err) => {
                            let _ = backend.child.kill();
                            let _ = backend.child.wait();
                            show_startup_error(&handle, &err);
                        }
                    }
                }
                Err(err) => show_startup_error(&handle, &err),
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build Writing Agent desktop")
        .run(|app, event| {
            if matches!(
                event,
                tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
            ) {
                app.state::<BackendState>().stop();
            }
        });
}
