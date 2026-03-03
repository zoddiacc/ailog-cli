#!/usr/bin/env bash
# ailog installer
# Usage: bash install.sh

set -e

INSTALL_DIR="$HOME/.local/bin"
AILOG_DIR="$HOME/.local/share/ailog"
CONFIG_DIR="$HOME/.config/ailog"

echo "Installing ailog — AI-powered Android/AOSP log interpreter"
echo ""

# Check Python 3.8+
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found."
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(sys.version_info.major * 10 + sys.version_info.minor)")
if [ "$PY_VERSION" -lt "38" ]; then
    echo "Error: Python 3.8+ required (found $(python3 --version))"
    exit 1
fi

echo "✓ Python $(python3 --version | cut -d' ' -f2) found"

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$AILOG_DIR"
mkdir -p "$CONFIG_DIR"

# Clean previous install
rm -rf "$AILOG_DIR/src"

# Copy source files
cp -r src/ "$AILOG_DIR/src/"
cp ailog.py "$AILOG_DIR/ailog.py"

# Copy example files if they exist
if [ -d "examples" ]; then
    cp -r examples/ "$AILOG_DIR/examples/"
fi

# Create launcher script
cat > "$INSTALL_DIR/ailog" << 'EOF'
#!/usr/bin/env bash
exec python3 "$HOME/.local/share/ailog/ailog.py" "$@"
EOF

chmod +x "$INSTALL_DIR/ailog"

echo "✓ Installed to $INSTALL_DIR/ailog"
echo "✓ Config directory: $CONFIG_DIR"
echo ""

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "⚠️  Add this to your ~/.bashrc or ~/.zshrc:"
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

echo "Quick start:"
echo ""
echo "  # Default: uses local Ollama (no API key needed)"
echo "  ailog config --show                    # View config"
echo "  ailog analyze build.log                # Analyze a log file"
echo ""
echo "  # Switch to a cloud provider:"
echo "  ailog config --provider openai --api-key sk-..."
echo "  ailog config --provider anthropic --api-key sk-ant-..."
echo ""
echo "  # Use Ollama (default, free, local):"
echo "  # 1. Install: https://ollama.com"
echo "  # 2. Pull a model: ollama pull qwen2.5-coder:3b"
echo "  # 3. Run: ailog analyze build.log"
echo ""
echo "  ailog --help                           # Full help"
