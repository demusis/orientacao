# ARIADNE Mobile (Android em Kotlin + Jetpack Compose + Núcleo em Rust)

Aplicativo Android nativo com telas em **Kotlin / Jetpack Compose (Material 3)** empacotado pelo **Gradle** e núcleo offline-first em **Rust** (`mobile/rust/`, biblioteca nativa `libariadne_core.so` via JNI).

## Arquitetura

- **Núcleo em Rust (`mobile/rust/`)**:
  - `src/db.rs`: persistência local em SQLite (`rusqlite` `bundled`) com cache de `orientacoes`, `marcos`, `atas`, `pareceres` e `fila_operacoes` (`op_id` UUID v4 + atualização otimista imediata).
  - `src/sync.rs`: cliente HTTP (`reqwest` + `rustls-tls`) que autentica (`POST /api/v1/auth/token`) e sincroniza (`GET` / `POST /api/v1/sync`) com o servidor ARIADNE no PythonAnywhere.
  - `src/lib.rs`: fachada JSON + exports JNI (`br.edu.ariadne.mobile.core.AriadneRustBridge`).
- **Interface Android (`mobile/app/`)**:
  - `MainActivity.kt`, `ui/AriadneScreens.kt`: telas em Material 3 (`#1B4B7A`) para login, fila offline, Tarefas, Reuniões/Atas e Pareceres, tanto para **orientador** quanto para **orientando**.
  - `core/AriadneRustBridge.kt` e `core/AriadneModels.kt`: ponte JNI e modelos desserializados.

## Compilação e testes

### 1. Testar e compilar o núcleo Rust (`libariadne_core.so`)

```powershell
cd mobile\rust
cargo test
cargo build --target aarch64-linux-android --release
copy "$env:LOCALAPPDATA\ariadne-rust-target\aarch64-linux-android\release\libariadne_core.so" ..\app\src\main\jniLibs\arm64-v8a\libariadne_core.so
```

*(Caso não defina `CARGO_TARGET_DIR`, o arquivo gerado fica em `mobile/rust/target/aarch64-linux-android/release/libariadne_core.so`.)*

### 2. Compilar e assinar o APK com Gradle

```powershell
cd mobile
$env:JAVA_HOME = "$env:LOCALAPPDATA\jdk-17"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
.\gradlew.bat assembleDebug
```

O APK assinado para depuração é gerado em `mobile/app/build/outputs/apk/debug/app-debug.apk`.
Para gerar o APK de release (após configurar a keystore em `signingConfigs`), execute `.\gradlew.bat assembleRelease`.

> **Nota para o servidor no PythonAnywhere:** atualize o código do servidor (`git pull`) e recarregue a aplicação web para expor as rotas `/api/v1/auth/token`, `/api/v1/sync` e `/api/v1/marcos/<id>/entrega` (envio de documento pela tarefa, só online; exige a feature `multipart` do `reqwest`, já declarada no `Cargo.toml`).
