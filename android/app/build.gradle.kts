import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

// Local, un-committed overrides: android/local.properties (gitignored) or a
// -P gradle property. The service token must never land in a commit.
val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) {
        file.inputStream().use { load(it) }
    }
}

fun configValue(name: String, fallback: String): String =
    localProperties.getProperty(name)
        ?: (project.findProperty(name) as String?)
        ?: fallback

// Retrofit requires a trailing slash; a missing one throws at build time of
// the client, which is a confusing way to learn about a typo'd property.
val storykeepBaseUrl = configValue("STORYKEEP_BASE_URL", "https://storykeep-production.up.railway.app/api/v1/")
    .let { if (it.endsWith("/")) it else "$it/" }

// Empty by default: the app builds, but every authenticated call 401s until a
// token is dropped into local.properties. Never commit a real value.
val storykeepServiceToken = configValue("STORYKEEP_SERVICE_TOKEN", "")

// These land in Kotlin string literals, so guard against quote injection from
// the property source.
fun kotlinStringLiteral(value: String): String =
    "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

android {
    namespace = "com.storykeep.junior"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.storykeep.junior"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0-shell"
        buildConfigField("String", "BASE_URL", kotlinStringLiteral(storykeepBaseUrl))
        buildConfigField("String", "SERVICE_TOKEN", kotlinStringLiteral(storykeepServiceToken))
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-process:2.8.7")
    implementation("androidx.navigation:navigation-compose:2.8.5")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // Network layer (slice 1): Retrofit + OkHttp, kotlinx.serialization.
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-kotlinx-serialization:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}
