# Release shrinking for the real app (slice 5).
# Rules only cover reflection / serialization surfaces this app actually uses:
# Retrofit service interfaces + @Serializable DTOs (network layer, slices 1-4),
# OkHttp (platform classes), kotlinx.coroutines, Compose runtime, and
# navigation-compose (@Navigator.Name is looked up reflectively).

# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------
# Keep line numbers so Steve can read release crash reports, but hide the
# original file names.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# ---------------------------------------------------------------------------
# Retrofit (com.squareup.retrofit2:retrofit:2.11.0)
# ---------------------------------------------------------------------------
# StorykeepApi (network/StorykeepApi.kt) is an interface built with
# retrofit.create(...); Retrofit reads the @GET/@POST/@Multipart/@Part/@Body/
# @Path annotations and method signatures reflectively at call time.
-keepattributes Signature, InnerClasses, EnclosingMethod
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations
-keepattributes AnnotationDefault
-dontwarn retrofit2.**
-keep,allowobfuscation,allowshrinking interface retrofit2.Call
-keep,allowobfuscation,allowshrinking class kotlin.coroutines.Continuation
# Keep every interface method annotated with a retrofit2.http.* annotation
# (and its parameters — they are matched by position).
-keepclasseswithmembers,allowobfuscation interface * {
    @retrofit2.http.* <methods>;
}

# ---------------------------------------------------------------------------
# OkHttp (com.squareup.okhttp3:okhttp:4.12.0 + logging-interceptor)
# ---------------------------------------------------------------------------
# OkHttp probes for optional platform integrations at runtime; they are absent
# on Android and only referenced by name.
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
-dontwarn javax.annotation.**
-dontwarn org.codehaus.mojo.animal_sniffer.**

# ---------------------------------------------------------------------------
# kotlinx.serialization (org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3)
# ---------------------------------------------------------------------------
# Every @Serializable DTO in network/StorykeepApi.kt (SttClipDto, ChatSpeechDto,
# JuniorShared*Dto, JuniorDocumentDto, ...) is serialized through the
# generated <T>$Companion.serializer(...) — looked up by reflection.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
# Keep the generated $$serializer classes of every @Serializable class in the
# app (they are resolved by name from the companion).
-keep,includedescriptorclasses class com.storykeep.junior.**$$serializer { *; }
-keepclassmembers class com.storykeep.junior.** {
    *** Companion;
}
-keepclasseswithmembers class com.storykeep.junior.** {
    kotlinx.serialization.KSerializer serializer(...);
}
# kotlinx.serialization runtime itself is Kotlin-code only; no reflection keep
# needed beyond the above, but silence missing-class noise from the plugin's
# generated code.
-dontwarn kotlinx.serialization.**

# ---------------------------------------------------------------------------
# kotlinx.coroutines (org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0)
# ---------------------------------------------------------------------------
-dontwarn kotlinx.coroutines.**

# ---------------------------------------------------------------------------
# Jetpack Compose (compose-bom 2024.12.01)
# ---------------------------------------------------------------------------
# The Compose compiler generates its own keep rules; these cover the runtime
# reflection surfaces that remain (composition provider lookup, preview
# rendering code paths that reach into ui.tooling at runtime in edge builds).
-keep class androidx.compose.runtime.** { *; }
-keep class androidx.compose.ui.tooling.preview.** { *; }
-dontwarn androidx.compose.**

# ---------------------------------------------------------------------------
# navigation-compose (androidx.navigation:navigation-compose:2.8.5)
# ---------------------------------------------------------------------------
# Custom navigators are discovered via the @Navigator.Name annotation, which
# is read reflectively by androidx.navigation.NavigatorProvider.
-keep @androidx.navigation.Navigator.Name class * { *; }
-keepnames class * extends androidx.navigation.Navigator
-keepnames class androidx.navigation.fragment.NavHostFragment
