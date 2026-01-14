# Termux System Monitor

A modern, feature-rich terminal UI dashboard for monitoring your Android device in Termux.

## Features

- 📊 **System Overview** - At-a-glance view of CPU, memory, storage, battery, and network
- 💻 **CPU Details** - Real-time usage, per-core frequencies, and processor info
- 🧠 **Memory Stats** - RAM and swap usage with detailed breakdowns
- 💾 **Storage Browser** - Interactive file explorer with disk usage statistics
- 🔋 **Battery Monitor** - Charge level, health, temperature, and time remaining
- 🌐 **Network Info** - Real-time upload/download speeds, IP addresses, and packet stats
- ⚙️ **Process Manager** - Top processes by CPU and memory usage
- 🎨 **Settings Panel** - Customize refresh rate, battery capacity, and more

## Installation

### Prerequisites

```bash
pkg update && pkg upgrade
pkg install python
```

### Install Dependencies

```bash
pip install rich psutil
```

### Download

```bash
curl -O https://raw.githubusercontent.com/AhmarZaidi/termux-status/main/status.py
chmod +x status.py
```

## Usage

### Run the Monitor

```bash
python status.py
```

### Navigation

- **↑/↓** - Switch between tabs
- **Enter** - Open file explorer (on Storage tab) or edit settings
- **←/→** - Adjust settings values (on Settings tab)
- **Esc** - Exit file explorer
- **r** - Reset settings to defaults (on Settings tab)
- **q** - Quit the monitor

### Optional: Add to PATH

```bash
mkdir -p ~/.local/bin
mv status.py ~/.local/bin/monitor
echo 'export PATH=$PATH:~/.local/bin' >> ~/.bashrc
source ~/.bashrc
```

Now run with:
```bash
monitor
```

## Screenshots

The dashboard features:
- Color-coded progress bars (green/yellow/red based on usage)
- Real-time data updates (configurable refresh rate)
- Smooth, flicker-free UI
- Rounded borders and modern design
- Icon-based tab navigation

## Requirements

- **Android** with Termux installed
- **Python 3.6+**
- **Termux API** (optional, for battery info): `pkg install termux-api`

## Settings

Customize the monitor behavior:
- **Refresh Rate**: 0.1s - 2.0s (default: 0.5s)
- **Battery Capacity**: Set your device's battery capacity for accurate time estimates
- **Show Icons**: Toggle emoji icons in the UI
- **Color Theme**: Choose between default, minimal, or dark themes

## Troubleshooting

**Battery info shows N/A:**
```bash
pkg install termux-api
```

**Permission errors:**
Some system files may not be accessible in Termux. The monitor handles these gracefully and uses alternative methods.

**UI appears distorted:**
Ensure your terminal supports Unicode and has sufficient width (minimum 80 columns recommended).

## License

MIT License - feel free to use and modify!

## Contributing

Issues and pull requests welcome [here](https://github.com/AhmarZaidi/termux-status/issues)
