use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;

/// 持有 sidecar 子进程引用，防止被 drop 后进程被 kill
struct SidecarProcesses(Mutex<Vec<CommandChild>>);

#[tauri::command]
fn get_runtime_url() -> String {
    "http://127.0.0.1:19800".to_string()
}

#[tauri::command]
fn get_backend_url() -> String {
    "http://127.0.0.1:8000".to_string()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .manage(SidecarProcesses(Mutex::new(vec![])))
        .invoke_handler(tauri::generate_handler![get_runtime_url, get_backend_url])
        .setup(|app| {
            let processes = app.state::<SidecarProcesses>();

            // 启动主后端服务（FastAPI，端口 8000）
            match app.shell().sidecar("agentteams-backend") {
                Ok(cmd) => match cmd.spawn() {
                    Ok((_rx, child)) => {
                        processes.0.lock().unwrap().push(child);
                        log::info!("agentteams-backend sidecar 已启动");
                    }
                    Err(e) => log::error!("启动 agentteams-backend 失败: {e}"),
                },
                Err(e) => log::error!("找不到 agentteams-backend sidecar: {e}"),
            }

            // 启动 Client Runtime（本地能力服务，端口 19800）
            match app.shell().sidecar("agentteams-runtime") {
                Ok(cmd) => match cmd.spawn() {
                    Ok((_rx, child)) => {
                        processes.0.lock().unwrap().push(child);
                        log::info!("agentteams-runtime sidecar 已启动");
                    }
                    Err(e) => log::error!("启动 agentteams-runtime 失败: {e}"),
                },
                Err(e) => log::error!("找不到 agentteams-runtime sidecar: {e}"),
            }

            #[cfg(debug_assertions)]
            {
                let window = app.get_webview_window("main").unwrap();
                window.open_devtools();
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("AgentTeams Desktop 启动失败");
}
