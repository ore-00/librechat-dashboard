#!/bin/bash

echo "Installing LibreChat Dashboard..."
echo ""

# Check if running on Arch-based system
if ! command -v pacman &> /dev/null; then
    echo "Warning: This installer is designed for Arch-based systems (CachyOS, Manjaro, etc.)"
    echo "You may need to manually install: PyQt6, PyQt6-Charts, and python-psutil"
    echo ""
fi

# Install dependencies via pacman
echo "Installing system dependencies via pacman..."
echo ""

packages_to_install=()

if ! python -c "import PyQt6" 2>/dev/null; then
    packages_to_install+=("python-pyqt6")
fi

if ! python -c "from PyQt6.QtCharts import QChart" 2>/dev/null; then
    packages_to_install+=("python-pyqt6-charts")
fi

if ! python -c "import psutil" 2>/dev/null; then
    packages_to_install+=("python-psutil")
fi

if [ ${#packages_to_install[@]} -gt 0 ]; then
    echo "Installing: ${packages_to_install[*]}"
    sudo pacman -S --needed "${packages_to_install[@]}"
    echo ""
else
    echo "✓ All dependencies already installed"
    echo ""
fi

# Verify installations
echo "Verifying installations..."
all_ok=true

if ! python -c "import PyQt6" 2>/dev/null; then
    echo "✗ PyQt6 installation failed"
    all_ok=false
else
    echo "✓ PyQt6 installed"
fi

if ! python -c "from PyQt6.QtCharts import QChart" 2>/dev/null; then
    echo "✗ PyQt6-Charts installation failed"
    all_ok=false
else
    echo "✓ PyQt6-Charts installed"
fi

if ! python -c "import psutil" 2>/dev/null; then
    echo "✗ python-psutil installation failed"
    all_ok=false
else
    echo "✓ python-psutil installed"
fi

echo ""

if [ "$all_ok" = false ]; then
    echo "Some dependencies failed to install. Please install manually:"
    echo "  sudo pacman -S python-pyqt6 python-pyqt6-charts python-psutil"
    exit 1
fi

# Copy the dashboard script
echo "Installing dashboard script..."
if [ ! -f "librechat-dashboard.py" ]; then
    echo "Error: librechat-dashboard.py not found in current directory"
    echo "Please run this script from the directory containing librechat-dashboard.py"
    exit 1
fi

sudo cp librechat-dashboard.py /usr/local/bin/librechat-dashboard
sudo chmod +x /usr/local/bin/librechat-dashboard

# Create desktop entry
echo "Creating desktop entry..."
mkdir -p ~/.local/share/applications

cat > ~/.local/share/applications/librechat-dashboard.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=LibreChat Dashboard
Comment=Monitor and manage LibreChat services
Exec=/usr/local/bin/librechat-dashboard
Icon=network-server-database
Terminal=false
Categories=System;Utility;Network;
EOF

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
fi

if command -v kbuildsycoca6 &> /dev/null; then
    kbuildsycoca6 --noincremental 2>/dev/null || true
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Installation complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "LibreChat Dashboard Features:"
echo "  • Dashboard Tab - Service cards with real-time stats"
echo "  • Monitoring Tab - CPU/RAM graphs (60s history)"
echo "  • Logs Tab - Consolidated logs from all services"
echo "  • One-click service management"
echo "  • System resource monitoring"
echo ""
echo "Launch options:"
echo "  1. Application menu: 'LibreChat Dashboard'"
echo "  2. Terminal: librechat-dashboard"
echo "  3. Pin to taskbar for quick access"
echo ""
echo "Note: You may need to log out/in for the application"
echo "      menu entry to appear in some desktop environments."
echo ""
