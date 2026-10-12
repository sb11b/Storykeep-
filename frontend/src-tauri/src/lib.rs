use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            // Desktop overlay bubble (slice 1): Ctrl+Alt+Space toggles the
            // transparent, always-on-top "overlay" window. The shortcut is
            // registered in setup so it exists before the first paint, and the
            // handler is attached through the plugin's own Builder. Desktop
            // only — the plugin has no Android/iOS build.
            #[cfg(desktop)]
            {
                use tauri_plugin_global_shortcut::{
                    Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState,
                };

                let toggle_overlay =
                    Shortcut::new(Some(Modifiers::CONTROL | Modifiers::ALT), Code::Space);

                app.handle().plugin(
                    tauri_plugin_global_shortcut::Builder::new()
                        .with_handler(move |app, shortcut, event| {
                            if shortcut != &toggle_overlay {
                                return;
                            }
                            if event.state() != ShortcutState::Pressed {
                                return;
                            }
                            // Handler stays tiny: show/hide the overlay window.
                            if let Some(overlay) = app.get_webview_window("overlay") {
                                if overlay.is_visible().unwrap_or(false) {
                                    let _ = overlay.hide();
                                } else {
                                    let _ = overlay.show();
                                    let _ = overlay.set_focus();
                                }
                            }
                        })
                        .build(),
                )?;

                app.global_shortcut().register(toggle_overlay)?;
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running StoryKeep");
}
