#!/data/data/com.termux/files/usr/bin/python3
"""
Termux System Monitor - Modern TUI Dashboard
Dependencies: rich, psutil
Install: pip install rich psutil
"""

import os
import sys
import time
import json
import subprocess
from datetime import datetime, timedelta
from threading import Thread, Lock
from typing import Dict, Optional

try:
    from rich.console import Console
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import BarColumn, Progress, TextColumn
    from rich.text import Text
    from rich.align import Align
    from rich import box
    import psutil
except ImportError:
    print("Missing dependencies. Install with:")
    print("pip install rich psutil")
    sys.exit(1)


class TermuxMonitor:
    """Main monitor class for Termux system information"""
    
    def __init__(self):
        self.console = Console()
        self.data_lock = Lock()
        self.running = True
        self.selected_tab = 0
        self.tabs = ["Overview", "CPU", "Memory", "Storage", "Battery", "Network", "Processes"]
        self.refresh_rate = 0.5  # seconds
        
        # Cached data
        self.system_data = {
            "cpu": {},
            "memory": {},
            "storage": {},
            "battery": {},
            "network": {},
            "processes": [],
            "device": {}
        }
        
        # Start data collection thread
        self.collector_thread = Thread(target=self._collect_data, daemon=True)
        self.collector_thread.start()
    
    def _safe_cmd(self, cmd: list, parse_json=False):
        """Execute command safely"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return json.loads(result.stdout) if parse_json else result.stdout.strip()
        except Exception:
            pass
        return None
    
    def _get_termux_battery(self) -> Dict:
        """Get battery information from termux-battery-status"""
        data = self._safe_cmd(["termux-battery-status"], parse_json=True)
        if data:
            return {
                "percentage": data.get("percentage", 0),
                "status": data.get("status", "Unknown"),
                "health": data.get("health", "Unknown"),
                "temperature": data.get("temperature", 0),
                "plugged": data.get("plugged", "Unknown"),
                "current": data.get("current", 0)
            }
        return {"percentage": 0, "status": "N/A", "health": "N/A", 
                "temperature": 0, "plugged": "N/A", "current": 0}
    
    def _get_device_info(self) -> Dict:
        """Get Android device information"""
        return {
            "model": self._safe_cmd(["getprop", "ro.product.model"]) or "Unknown",
            "android": self._safe_cmd(["getprop", "ro.build.version.release"]) or "Unknown",
            "sdk": self._safe_cmd(["getprop", "ro.build.version.sdk"]) or "Unknown",
            "manufacturer": self._safe_cmd(["getprop", "ro.product.manufacturer"]) or "Unknown",
            "arch": self._safe_cmd(["getprop", "ro.product.cpu.abi"]) or "Unknown",
            "kernel": os.uname().release
        }
    
    def _get_network_info(self) -> Dict:
        """Get network information"""
        net_io = psutil.net_io_counters()
        addrs = psutil.net_if_addrs()
        
        ip_addr = "N/A"
        if "wlan0" in addrs:
            for addr in addrs["wlan0"]:
                if addr.family == 2:  # AF_INET
                    ip_addr = addr.address
                    break
        
        return {
            "ip": ip_addr,
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv
        }
    
    def _collect_data(self):
        """Background thread to collect system data"""
        last_net = {"sent": 0, "recv": 0, "time": time.time()}
        
        while self.running:
            try:
                # CPU data
                cpu_percent = psutil.cpu_percent(interval=0.1, percpu=True)
                cpu_freq = psutil.cpu_freq()
                
                with self.data_lock:
                    self.system_data["cpu"] = {
                        "percent": sum(cpu_percent) / len(cpu_percent),
                        "per_core": cpu_percent,
                        "count": psutil.cpu_count(),
                        "freq": cpu_freq.current if cpu_freq else 0,
                        "freq_max": cpu_freq.max if cpu_freq else 0
                    }
                    
                    # Memory data
                    mem = psutil.virtual_memory()
                    swap = psutil.swap_memory()
                    self.system_data["memory"] = {
                        "total": mem.total,
                        "available": mem.available,
                        "used": mem.used,
                        "percent": mem.percent,
                        "swap_total": swap.total,
                        "swap_used": swap.used,
                        "swap_percent": swap.percent
                    }
                    
                    # Storage data
                    storage = psutil.disk_usage("/data")
                    self.system_data["storage"] = {
                        "total": storage.total,
                        "used": storage.used,
                        "free": storage.free,
                        "percent": storage.percent
                    }
                    
                    # Battery data
                    self.system_data["battery"] = self._get_termux_battery()
                    
                    # Network data with speed calculation
                    net_info = self._get_network_info()
                    current_time = time.time()
                    time_diff = current_time - last_net["time"]
                    
                    net_info["speed_up"] = (net_info["bytes_sent"] - last_net["sent"]) / time_diff if time_diff > 0 else 0
                    net_info["speed_down"] = (net_info["bytes_recv"] - last_net["recv"]) / time_diff if time_diff > 0 else 0
                    
                    last_net = {
                        "sent": net_info["bytes_sent"],
                        "recv": net_info["bytes_recv"],
                        "time": current_time
                    }
                    self.system_data["network"] = net_info
                    
                    # Device info (static, update less frequently)
                    if not self.system_data["device"]:
                        self.system_data["device"] = self._get_device_info()
                    
                    # Process data
                    procs = []
                    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                        try:
                            pinfo = proc.info
                            if pinfo['cpu_percent'] is not None and pinfo['cpu_percent'] > 0:
                                procs.append(pinfo)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    
                    procs.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
                    self.system_data["processes"] = procs[:10]
                
                time.sleep(self.refresh_rate)
                
            except Exception as e:
                time.sleep(1)
    
    def _format_bytes(self, bytes_val: float) -> str:
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f}PB"
    
    def _format_speed(self, bytes_per_sec: float) -> str:
        """Format network speed"""
        return f"{self._format_bytes(bytes_per_sec)}/s"
    
    def _create_progress_bar(self, value: float, total: float = 100, width: int = 30) -> str:
        """Create a colored progress bar"""
        percent = (value / total * 100) if total > 0 else 0
        filled = int(width * value / total) if total > 0 else 0
        
        # Color based on percentage
        if percent >= 90:
            color = "red"
        elif percent >= 70:
            color = "yellow"
        else:
            color = "green"
        
        bar = "█" * filled + "░" * (width - filled)
        return f"[{color}]{bar}[/{color}]"
    
    def _make_header_panel(self) -> Panel:
        """Create header with title and time"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        uptime_str = str(uptime).split('.')[0]
        
        header_text = Text()
        header_text.append("🚀 ", style="bold magenta")
        header_text.append("Termux System Monitor", style="bold cyan")
        header_text.append(f"  •  {current_time}", style="dim")
        header_text.append(f"  •  ⏱️  Uptime: {uptime_str}", style="green")
        
        return Panel(Align.center(header_text), box=box.ROUNDED, style="cyan")
    
    def _make_tabs_panel(self) -> Panel:
        """Create tabs navigation panel"""
        tabs_text = Text()
        for i, tab in enumerate(self.tabs):
            if i == self.selected_tab:
                tabs_text.append(f" ▶ {tab} ", style="bold green on black")
            else:
                tabs_text.append(f"   {tab} ", style="dim")
            tabs_text.append("\n")
        
        tabs_text.append("\n", style="dim")
        tabs_text.append("↑/↓: Navigate  q: Quit", style="dim italic")
        
        return Panel(tabs_text, title="[bold]Navigation[/bold]", box=box.ROUNDED, style="blue")
    
    def _make_overview_panel(self) -> Panel:
        """Create overview panel"""
        with self.data_lock:
            data = self.system_data.copy()
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", style="white")
        table.add_column("Bar", style="white", width=35)
        
        # CPU
        cpu_pct = data["cpu"].get("percent", 0)
        table.add_row(
            "💻 CPU Usage",
            f"{cpu_pct:.1f}%",
            self._create_progress_bar(cpu_pct)
        )
        
        # Memory
        mem_pct = data["memory"].get("percent", 0)
        mem_used = self._format_bytes(data["memory"].get("used", 0))
        mem_total = self._format_bytes(data["memory"].get("total", 1))
        table.add_row(
            "🧠 Memory",
            f"{mem_used} / {mem_total}",
            self._create_progress_bar(mem_pct)
        )
        
        # Storage
        stor_pct = data["storage"].get("percent", 0)
        stor_used = self._format_bytes(data["storage"].get("used", 0))
        stor_total = self._format_bytes(data["storage"].get("total", 1))
        table.add_row(
            "💾 Storage",
            f"{stor_used} / {stor_total}",
            self._create_progress_bar(stor_pct)
        )
        
        # Battery
        bat_pct = data["battery"].get("percentage", 0)
        bat_status = data["battery"].get("status", "N/A")
        bat_icon = "⚡" if "CHARGING" in bat_status.upper() else "🔋" if bat_pct > 20 else "🪫"
        table.add_row(
            f"{bat_icon} Battery",
            f"{bat_pct}% ({bat_status})",
            self._create_progress_bar(bat_pct)
        )
        
        # Network speeds
        net_up = self._format_speed(data["network"].get("speed_up", 0))
        net_down = self._format_speed(data["network"].get("speed_down", 0))
        table.add_row("", "", "")
        table.add_row("📤 Upload Speed", net_up, "")
        table.add_row("📥 Download Speed", net_down, "")
        
        # Device info
        device = data["device"]
        table.add_row("", "", "")
        table.add_row("📱 Device", f"{device.get('manufacturer', '')} {device.get('model', '')}", "")
        table.add_row("🤖 Android", f"Version {device.get('android', '')} (SDK {device.get('sdk', '')})", "")
        table.add_row("🏗️  Architecture", device.get('arch', 'N/A'), "")
        table.add_row("🌐 IP Address", data["network"].get("ip", "N/A"), "")
        
        return Panel(table, title="[bold]📊 System Overview[/bold]", box=box.ROUNDED)
    
    def _make_cpu_panel(self) -> Panel:
        """Create detailed CPU panel"""
        with self.data_lock:
            cpu_data = self.system_data["cpu"].copy()
        
        table = Table(show_header=True, box=box.SIMPLE)
        table.add_column("Core", style="cyan", justify="center")
        table.add_column("Usage", style="white", justify="right")
        table.add_column("Bar", style="white", width=30)
        
        per_core = cpu_data.get("per_core", [])
        for i, usage in enumerate(per_core):
            table.add_row(
                f"Core {i}",
                f"{usage:.1f}%",
                self._create_progress_bar(usage)
            )
        
        # Add summary
        avg_usage = cpu_data.get("percent", 0)
        freq = cpu_data.get("freq", 0)
        freq_max = cpu_data.get("freq_max", 0)
        
        info = Text()
        info.append("\n")
        info.append(f"Average Usage: ", style="dim")
        info.append(f"{avg_usage:.1f}%\n", style="bold green")
        info.append(f"CPU Cores: ", style="dim")
        info.append(f"{cpu_data.get('count', 0)}\n", style="bold")
        if freq > 0:
            info.append(f"Current Frequency: ", style="dim")
            info.append(f"{freq:.0f} MHz\n", style="bold")
        if freq_max > 0:
            info.append(f"Max Frequency: ", style="dim")
            info.append(f"{freq_max:.0f} MHz", style="bold")
        
        combined = Table.grid()
        combined.add_row(table)
        combined.add_row(info)
        
        return Panel(combined, title="[bold]💻 CPU Details[/bold]", box=box.ROUNDED)
    
    def _make_memory_panel(self) -> Panel:
        """Create detailed memory panel"""
        with self.data_lock:
            mem_data = self.system_data["memory"].copy()
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Type", style="cyan", width=15)
        table.add_column("Used", style="white", width=12)
        table.add_column("Total", style="white", width=12)
        table.add_column("Percent", style="white", width=10)
        table.add_column("Bar", style="white", width=30)
        
        # RAM
        table.add_row(
            "🧠 RAM",
            self._format_bytes(mem_data.get("used", 0)),
            self._format_bytes(mem_data.get("total", 1)),
            f"{mem_data.get('percent', 0):.1f}%",
            self._create_progress_bar(mem_data.get("percent", 0))
        )
        
        # Available
        table.add_row(
            "  Available",
            self._format_bytes(mem_data.get("available", 0)),
            "",
            "",
            ""
        )
        
        table.add_row("", "", "", "", "")
        
        # Swap
        swap_total = mem_data.get("swap_total", 0)
        if swap_total > 0:
            table.add_row(
                "💿 Swap",
                self._format_bytes(mem_data.get("swap_used", 0)),
                self._format_bytes(swap_total),
                f"{mem_data.get('swap_percent', 0):.1f}%",
                self._create_progress_bar(mem_data.get("swap_percent", 0))
            )
        else:
            table.add_row("💿 Swap", "Not configured", "", "", "")
        
        return Panel(table, title="[bold]🧠 Memory Details[/bold]", box=box.ROUNDED)
    
    def _make_storage_panel(self) -> Panel:
        """Create storage panel"""
        with self.data_lock:
            stor_data = self.system_data["storage"].copy()
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", style="white")
        
        table.add_row("💾 Total Space", self._format_bytes(stor_data.get("total", 0)))
        table.add_row("📊 Used Space", self._format_bytes(stor_data.get("used", 0)))
        table.add_row("📂 Free Space", self._format_bytes(stor_data.get("free", 0)))
        table.add_row("📈 Usage Percent", f"{stor_data.get('percent', 0):.1f}%")
        
        # Visual bar
        bar_text = Text("\n")
        bar_text.append(self._create_progress_bar(stor_data.get("percent", 0), width=50))
        
        combined = Table.grid()
        combined.add_row(table)
        combined.add_row(bar_text)
        
        return Panel(combined, title="[bold]💾 Storage Details[/bold]", box=box.ROUNDED)
    
    def _make_battery_panel(self) -> Panel:
        """Create detailed battery panel"""
        with self.data_lock:
            bat_data = self.system_data["battery"].copy()
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", style="white")
        
        percentage = bat_data.get("percentage", 0)
        status = bat_data.get("status", "N/A")
        
        # Icon based on status
        if "CHARGING" in status.upper():
            icon = "⚡"
            color = "yellow"
        elif percentage > 80:
            icon = "🔋"
            color = "green"
        elif percentage > 20:
            icon = "🔋"
            color = "yellow"
        else:
            icon = "🪫"
            color = "red"
        
        table.add_row(f"{icon} Charge Level", f"[{color}]{percentage}%[/{color}]")
        table.add_row("⚙️  Status", status)
        table.add_row("💚 Health", bat_data.get("health", "N/A"))
        table.add_row("🌡️  Temperature", f"{bat_data.get('temperature', 0):.1f}°C")
        table.add_row("🔌 Plugged", bat_data.get("plugged", "N/A"))
        
        current = bat_data.get("current", 0)
        if current != 0:
            table.add_row("⚡ Current", f"{current} mA")
        
        # Visual bar
        bar_text = Text("\n")
        bar_text.append(self._create_progress_bar(percentage, width=50))
        
        combined = Table.grid()
        combined.add_row(table)
        combined.add_row(bar_text)
        
        return Panel(combined, title="[bold]🔋 Battery Details[/bold]", box=box.ROUNDED)
    
    def _make_network_panel(self) -> Panel:
        """Create network panel"""
        with self.data_lock:
            net_data = self.system_data["network"].copy()
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="cyan", width=25)
        table.add_column("Value", style="white")
        
        table.add_row("🌐 IP Address", net_data.get("ip", "N/A"))
        table.add_row("", "")
        table.add_row("📤 Upload Speed", f"[green]{self._format_speed(net_data.get('speed_up', 0))}[/green]")
        table.add_row("📥 Download Speed", f"[blue]{self._format_speed(net_data.get('speed_down', 0))}[/blue]")
        table.add_row("", "")
        table.add_row("📊 Total Sent", self._format_bytes(net_data.get("bytes_sent", 0)))
        table.add_row("📊 Total Received", self._format_bytes(net_data.get("bytes_recv", 0)))
        table.add_row("", "")
        table.add_row("📦 Packets Sent", f"{net_data.get('packets_sent', 0):,}")
        table.add_row("📦 Packets Received", f"{net_data.get('packets_recv', 0):,}")
        
        return Panel(table, title="[bold]🌐 Network Details[/bold]", box=box.ROUNDED)
    
    def _make_processes_panel(self) -> Panel:
        """Create top processes panel"""
        with self.data_lock:
            procs = self.system_data["processes"][:10]
        
        table = Table(show_header=True, box=box.SIMPLE)
        table.add_column("PID", style="cyan", justify="right", width=8)
        table.add_column("Name", style="white", width=30)
        table.add_column("CPU %", style="yellow", justify="right", width=10)
        table.add_column("MEM %", style="green", justify="right", width=10)
        
        for proc in procs:
            table.add_row(
                str(proc.get('pid', '')),
                proc.get('name', 'N/A')[:28],
                f"{proc.get('cpu_percent', 0):.1f}",
                f"{proc.get('memory_percent', 0):.1f}"
            )
        
        return Panel(table, title="[bold]⚙️  Top Processes[/bold]", box=box.ROUNDED)
    
    def _get_content_panel(self) -> Panel:
        """Get content based on selected tab"""
        tab_name = self.tabs[self.selected_tab]
        
        if tab_name == "Overview":
            return self._make_overview_panel()
        elif tab_name == "CPU":
            return self._make_cpu_panel()
        elif tab_name == "Memory":
            return self._make_memory_panel()
        elif tab_name == "Storage":
            return self._make_storage_panel()
        elif tab_name == "Battery":
            return self._make_battery_panel()
        elif tab_name == "Network":
            return self._make_network_panel()
        elif tab_name == "Processes":
            return self._make_processes_panel()
        
        return Panel("Content not available", box=box.ROUNDED)
    
    def _create_layout(self) -> Layout:
        """Create the main layout"""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
        )
        
        layout["body"].split_row(
            Layout(name="content", ratio=3),
            Layout(name="sidebar", ratio=1, minimum_size=25),
        )
        
        # Update panels
        layout["header"].update(self._make_header_panel())
        layout["content"].update(self._get_content_panel())
        layout["sidebar"].update(self._make_tabs_panel())
        
        return layout
    
    def _handle_input(self):
        """Handle keyboard input in a non-blocking way"""
        import termios
        import tty
        
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())
            
            # Check if input is available
            import select
            if select.select([sys.stdin], [], [], 0)[0]:
                char = sys.stdin.read(1)
                
                if char == '\x1b':  # ESC sequence
                    char += sys.stdin.read(2)
                    if char == '\x1b[A':  # Up arrow
                        self.selected_tab = (self.selected_tab - 1) % len(self.tabs)
                    elif char == '\x1b[B':  # Down arrow
                        self.selected_tab = (self.selected_tab + 1) % len(self.tabs)
                elif char.lower() == 'q':
                    self.running = False
                    
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    
    def run(self):
        """Main run loop"""
        try:
            with Live(self._create_layout(), console=self.console, refresh_per_second=4, screen=True) as live:
                while self.running:
                    self._handle_input()
                    live.update(self._create_layout())
                    time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            self.console.clear()
            self.console.print("[green]✨ Termux Monitor closed. Have a great day![/green]")


def main():
    """Entry point"""
    try:
        monitor = TermuxMonitor()
        monitor.run()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()