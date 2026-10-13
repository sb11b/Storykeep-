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

                if let Err(error) = app.handle().plugin(
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
                ) {
                    // A global shortcut is a convenience, never a requirement:
                    // registration fails when another program already holds
                    // Ctrl+Alt+Space (or a zombie instance still owns it) —
                    // that must never crash startup, so log and carry on.
                    eprintln!(
                        "[storykeep] global-shortcut plugin unavailable, overlay hotkey disabled: {error}"
                    );
                }

                if let Err(error) = app.global_shortcut().register(toggle_overlay) {
                    eprintln!(
                        "[storykeep] could not register Ctrl+Alt+Space, overlay hotkey disabled: {error}"
                    );
                }

                // Desktop auto-update: click-to-install updates from GitHub
                // Releases. The pubkey and the endpoint live in
                // tauri.conf.json (plugins.updater) — nothing to configure
                // here beyond registration. Desktop-only, same as the
                // shortcut above, so it sits in the same cfg block instead
                // of the top-level Builder chain. The JS side
                // (@tauri-apps/plugin-updater, see src/lib/auto-update.ts)
                // only ever calls check() and downloadAndInstall() after an
                // explicit user click on the update banner.
                app.handle()
                    .plugin(tauri_plugin_updater::Builder::new().build())?;
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running StoryKeep");
}
