//! Coquille Tauri du Terminal PEA.
//!
//! La fenêtre affiche le frontend ; les données proviennent du backend Python
//! local. Celui-ci est démarré au lancement et arrêté avec l'application, pour
//! que l'utilisateur n'ait pas à gérer deux processus à la main.

use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{Manager, RunEvent};

/// Port d'écoute du backend. Doit rester aligné avec `settings.port` côté
/// Python et avec `BACKEND` côté frontend.
const BACKEND_PORT: u16 = 8801;

/// Processus backend, conservé pour pouvoir l'arrêter à la fermeture.
struct Backend(Mutex<Option<Child>>);

/// Localise l'interpréteur Python à utiliser.
///
/// En développement, l'environnement virtuel du dépôt ; en production, un
/// interpréteur embarqué à côté de l'exécutable. La variable d'environnement
/// `PEATERM_PYTHON` permet de forcer un chemin.
fn find_python(resource_dir: &Path) -> Option<PathBuf> {
    if let Ok(explicit) = std::env::var("PEATERM_PYTHON") {
        let path = PathBuf::from(explicit);
        if path.exists() {
            return Some(path);
        }
    }

    let candidates = [
        resource_dir.join("python/python.exe"),
        resource_dir.join("../.venv/Scripts/python.exe"),
        // Arborescence de développement : src-tauri/target/debug -> racine du dépôt.
        resource_dir.join("../../../../../../.venv/Scripts/python.exe"),
    ];
    candidates.into_iter().find(|path| path.exists())
}

/// Localise le dossier du backend Python.
fn find_backend_dir(resource_dir: &Path) -> Option<PathBuf> {
    let candidates = [
        resource_dir.join("backend"),
        resource_dir.join("../../../../../backend"),
        resource_dir.join("../../../../../../terminal/backend"),
    ];
    candidates
        .into_iter()
        .find(|path| path.join("app/main.py").exists())
}

fn spawn_backend(resource_dir: &Path) -> Option<Child> {
    let python = find_python(resource_dir)?;
    let backend_dir = find_backend_dir(resource_dir)?;

    let mut command = Command::new(python);
    command
        .current_dir(&backend_dir)
        .args([
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            &BACKEND_PORT.to_string(),
        ]);

    #[cfg(windows)]
    {
        // Sans cela, une console noire s'ouvre derrière la fenêtre.
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    command.spawn().ok()
}

/// Indique au frontend où joindre le backend.
#[tauri::command]
fn backend_url() -> String {
    format!("http://127.0.0.1:{BACKEND_PORT}")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(Backend(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![backend_url])
        .setup(|app| {
            let resource_dir = app
                .path()
                .resource_dir()
                .unwrap_or_else(|_| PathBuf::from("."));
            if let Some(child) = spawn_backend(&resource_dir) {
                *app.state::<Backend>().0.lock().unwrap() = Some(child);
            } else {
                // L'application reste utilisable si un backend tourne déjà,
                // ce qui est le cas courant en développement.
                eprintln!(
                    "Backend non démarré automatiquement : lancer uvicorn manuellement \
                     depuis terminal/backend, ou définir PEATERM_PYTHON."
                );
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("échec du démarrage de l'application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                // Ne pas laisser un serveur orphelin derrière soi.
                if let Some(mut child) = app_handle.state::<Backend>().0.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}
