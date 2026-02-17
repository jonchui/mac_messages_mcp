#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$HOME/Applications/MacMessagesMCP.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
LAUNCHER="$MACOS_DIR/macmessagesmcp-launcher"
INFO_PLIST="$CONTENTS_DIR/Info.plist"

mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

cat > "$INFO_PLIST" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>MacMessagesMCP</string>
  <key>CFBundleExecutable</key>
  <string>macmessagesmcp-launcher</string>
  <key>CFBundleIdentifier</key>
  <string>com.jonchui.macmessagesmcp</string>
  <key>CFBundleName</key>
  <string>MacMessagesMCP</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSBackgroundOnly</key>
  <true/>
</dict>
</plist>
PLIST

cat > "$LAUNCHER" <<'LAUNCHER'
#!/usr/bin/env zsh
set -euo pipefail
exec "$HOME/bin/start_mcp_proxy.sh"
LAUNCHER

chmod +x "$LAUNCHER"

echo "✅ Installed app wrapper at: $APP_DIR"
echo "Next: System Settings -> Privacy & Security -> Full Disk Access -> add $APP_DIR"
