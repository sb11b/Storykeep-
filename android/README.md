# Storykeep Android (days 1–3 shell)

Kotlin + Jetpack Compose app. Three screens only: Home, Conversation, Stories.

No Grok Voice / Speech-to-Speech. No account wall, wake word, family sharing, or film tools. Talk, Type, and Save as story use a **local fake transcript** so you can walk the shell on a device.

This folder is a separate Gradle project. It is not part of the Railway web image (`Dockerfile` / `railway.toml` still build backend + Next.js only).

## Open and run in Android Studio

1. Install [Android Studio](https://developer.android.com/studio) (Ladybug / 2024.2 or newer is fine).
2. **File → Open** and choose the `android` directory in this repo (not the repo root).
3. Let Gradle sync. If asked, use the embedded JDK 17+ and install SDK 35.
4. Plug in a phone (USB debugging) or start an emulator with **API 26 or higher**.
5. Select the `app` run configuration and press **Run**.

Command line, after the Android SDK is installed and `ANDROID_HOME` is set:

```bash
cd android
./gradlew :app:installDebug
```

On Windows: `gradlew.bat :app:installDebug`.

## What you can walk

- **Home:** mark, “Junior is here”, presence orb, Talk / Type, last-spoke placeholder, bottom nav Talk / Stories / Keep.
- **Talk** opens Conversation with the mic stub. Tap the amber control: Idle → Listening → fake transcript → Speaking.
- **Type** opens Conversation with the keyboard up, mic off, Listen off, sound off.
- **Save as story** appends the current transcript (text only) to Stories. **End** and **Back** return Home and clear the stub session.
- **Stories:** pinned week’s question, Answer by talking / typing, cards, Record a story.

Keep is not a fourth screen; it returns to Home.
