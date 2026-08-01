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

/// Cherche un chemin relatif dans le dossier de départ puis dans chacun de ses
/// ancêtres.
///
/// Remonter l'arborescence plutôt que coder des `../../..` en dur : la
/// profondeur de `resource_dir` diffère entre l'exécution en développement
/// (`target/release`) et l'application installée, et un décalage d'un seul
/// niveau suffit à ne rien trouver.
fn find_upwards(start: &Path, relative: &str, max_depth: usize) -> Option<PathBuf> {
    let mut current = Some(start);
    for _ in 0..max_depth {
        let dir = current?;
        let candidate = dir.join(relative);
        if candidate.exists() {
            return Some(candidate);
        }
        current = dir.parent();
    }
    None
}

/// Localise l'interpréteur Python à utiliser.
///
/// En production, un interpréteur embarqué à côté de l'exécutable ; en
/// développement, l'environnement virtuel du dépôt. `PEATERM_PYTHON` permet de
/// forcer un chemin.
fn find_python(resource_dir: &Path) -> Option<PathBuf> {
    if let Ok(explicit) = std::env::var("PEATERM_PYTHON") {
        let path = PathBuf::from(explicit);
        if path.exists() {
            return Some(path);
        }
    }

    let embedded = resource_dir.join("python/python.exe");
    if embedded.exists() {
        return Some(embedded);
    }

    find_upwards(resource_dir, ".venv/Scripts/python.exe", 8)
        .or_else(|| find_upwards(resource_dir, ".venv/bin/python", 8))
}

/// Localise le dossier du backend Python.
fn find_backend_dir(resource_dir: &Path) -> Option<PathBuf> {
    let bundled = resource_dir.join("backend");
    if bundled.join("app/main.py").exists() {
        return Some(bundled);
    }

    find_upwards(resource_dir, "terminal/backend/app/main.py", 8)
        .or_else(|| find_upwards(resource_dir, "backend/app/main.py", 8))
        .and_then(|main| main.parent()?.parent().map(Path::to_path_buf))
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

    let child = command.spawn().ok()?;

    #[cfg(windows)]
    attach_to_job(&child);

    Some(child)
}

/// Rattache le backend à un objet de travail configuré pour tuer ses membres
/// quand le dernier descripteur se ferme.
///
/// Fermer la fenêtre suffit normalement à arrêter le backend, mais un arrêt
/// brutal — plantage, `Stop-Process -Force`, fin de session — laisse sinon un
/// serveur orphelin qui retient le port et bloque le lancement suivant. Le
/// descripteur de l'objet de travail se ferme avec le processus quoi qu'il
/// arrive : c'est le système qui fait alors le ménage.
#[cfg(windows)]
fn attach_to_job(child: &Child) {
    use std::os::windows::io::AsRawHandle;

    use windows::Win32::Foundation::HANDLE;
    use windows::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    unsafe {
        let Ok(job) = CreateJobObjectW(None, windows::core::PCWSTR::null()) else {
            return;
        };

        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

        if SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &limits as *const _ as *const std::ffi::c_void,
            std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        )
        .is_err()
        {
            return;
        }

        let _ = AssignProcessToJobObject(job, HANDLE(child.as_raw_handle() as _));

        // `job` n'est volontairement jamais fermé : `HANDLE` est un simple
        // entier sans destructeur, donc ne pas appeler `CloseHandle` suffit à
        // le garder ouvert jusqu'à la fin du processus. C'est précisément sa
        // fermeture par le système, à ce moment-là, qui tue le backend.
    }
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
