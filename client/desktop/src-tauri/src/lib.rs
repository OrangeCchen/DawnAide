use tauri::Manager;

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
        .invoke_handler(tauri::generate_handler![get_runtime_url, get_backend_url])
        .setup(|app| {
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
