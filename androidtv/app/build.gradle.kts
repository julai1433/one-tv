plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// La app de One TV para la TV: Google TV, Android TV y Fire TV (Kotlin + Jetpack Compose + Media3).
android {
    namespace = "app.onetv.tv"
    // Compose (BOM 2026.09) y core-ktx 1.19 piden compilar contra la API 37; la app se comporta como API 36.
    compileSdk = 37
    compileSdkMinor = 2

    defaultConfig {
        applicationId = "app.onetv.tv"
        // 23 (Android 6) es lo mínimo que piden hoy AndroidX, Compose y Media3. Cubre todo Google TV
        // (Android 10 o más nuevo), Android TV desde 2016 y Fire TV con Fire OS 6, 7 y 8 (Fire TV Stick 4K de 2018
        // en adelante, Fire TV Stick de 3.ª generación, Lite, Cube y las TV con Fire TV de esos años).
        minSdk = 23
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Firmada con la llave de depuración para poder instalarla en una TV sin pasos extra (fase 1).
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }

    // Las letras y los íconos (Lucide, en blanco) son los mismos de la app del Roku: se toman de roku/, así hay
    // una sola copia en el proyecto. Quedan en la raíz de los «assets» de la app («Archivo-Bold.ttf», «play.png»).
    sourceSets {
        getByName("main") {
            assets.directories.add("../../roku/fonts")
            assets.directories.add("../../roku/images/icons")
        }
    }

    testOptions {
        unitTests.all { test ->
            test.testLogging {
                events("failed", "skipped")
                exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
            }
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.foundation)
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.exoplayer.hls)
    implementation(libs.media3.ui)

    testImplementation(libs.junit4)
    testImplementation(libs.org.json)
}
