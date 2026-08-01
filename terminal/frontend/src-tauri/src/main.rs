// Empêche l'ouverture d'une console Windows en plus de la fenêtre.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    pea_terminal_lib::run()
}
