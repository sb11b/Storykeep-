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
