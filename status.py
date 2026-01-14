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
import fcntl
import subprocess
from datetime import datetime, timedelta
from threading import Thread, Lock
from typing import Dict, Optional, List, Tuple
from pathlib import Path

try:
    from rich.console import Console
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
    from rich.text import Text
    from rich.align import Align
    from rich import box
    from rich.columns import Columns
    from rich.tree import Tree
    import psutil
except ImportError:
    print("Missing dependencies. Install with:")
    print("pip install rich psutil")
    sys.exit(1)


class FileExplorer:
    """File explorer for storage tab"""
    
    def __init__(self, start_path="/data/data/com.termux/files/home"):
        self.current_path = Path(start_path)
        self.selected_index = 0
        self.scroll_offset = 0
        self.items = []
        self.focused = False
        self._refresh_items()
    
    def _refresh_items(self):
        """Refresh directory listing"""
        try:
            self.items = [("📁", "..", self.current_path.parent, True, 0, 0)]
            
            # Get all items
            all_items = []
            for item in self.current_path.iterdir():
                try:
                    is_dir = item.is_dir()
                    size = 0
                    count = 0
                    
                    if is_dir:
                        # Count items in directory
                        try:
                            count = len(list(item.iterdir()))
                        except PermissionError:
                            count = 0
                        icon = "📁"
                    else:
                        size = item.stat().st_size
                        icon = self._get_file_icon(item.name)
                    
                    all_items.append((icon, item.name, item, is_dir, size, count))
                except PermissionError:
                    pass
            
            # Sort: directories first, then by name
            all_items.sort(key=lambda x: (not x[3], x[1].lower()))
            self.items.extend(all_items)
            
        except PermissionError:
            self.items = [("📁", "..", self.current_path.parent, True, 0, 0)]
    
    def _get_file_icon(self, filename: str) -> str:
        """Get icon based on file extension"""
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        icons = {
            'py': '🐍', 'sh': '📜', 'txt': '📄', 'md': '📝',
            'jpg': '🖼️', 'png': '🖼️', 'gif': '🖼️',
            'zip': '📦', 'tar': '📦', 'gz': '📦',
            'mp3': '🎵', 'mp4': '🎬', 'pdf': '📕'
        }
        return icons.get(ext, '📄')
    
    def navigate_up(self):
        if self.selected_index > 0:
            self.selected_index -= 1
    
    def navigate_down(self):
        if self.selected_index < len(self.items) - 1:
            self.selected_index += 1
    
    def enter_item(self):
        if self.items and self.selected_index < len(self.items):
            _, name, path, is_dir, _, _ = self.items[self.selected_index]
            if is_dir:
                try:
                    self.current_path = path
                    self.selected_index = 0
                    self.scroll_offset = 0
                    self._refresh_items()
                except PermissionError:
                    pass
    
    def get_display_items(self, max_items: int = 15) -> List:
        """Get items to display with scrolling"""
        # Adjust scroll offset
        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + max_items:
            self.scroll_offset = self.selected_index - max_items + 1
        
        return self.items[self.scroll_offset:self.scroll_offset + max_items]


class TermuxMonitor:
    """Main monitor class for Termux system information"""
    
    def __init__(self):
        self.console = Console()
        self.data_lock = Lock()
        self.running = True
        self.selected_tab = 0
        self.tabs = [
            ("📊", "Overview"),
            ("💻", "CPU"),
            ("🧠", "Memory"),
            ("💾", "Storage"),
            ("🔋", "Battery"),
            ("🌐", "Network"),
            ("⚙️", "Processes")
        ]
        self.refresh_rate = 0.5
        
        # UI dimensions
        self.ui_height = 20
        self.sidebar_width = 8
        
        # File explorer
        self.file_explorer = FileExplorer()
        
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
        
        # For CPU calculation using /proc/stat alternative
        self.last_cpu_times = {"user": 0, "system": 0, "idle": 0}
        self.last_net_io = {"sent": 0, "recv": 0, "time": time.time()}
        
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
    
    def _get_cpu_usage_from_times(self) -> Tuple[float, List[float]]:
        """Calculate CPU usage from process times"""
        try:
            # Get CPU times for all processes
            total_user = 0
            total_system = 0
            
            for proc in psutil.process_iter(['cpu_times']):
                try:
                    times = proc.info['cpu_times']
                    if times:
                        total_user += times.user
                        total_system += times.system
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Calculate delta
            user_delta = total_user - self.last_cpu_times["user"]
            system_delta = total_system - self.last_cpu_times["system"]
            
            # Update last values
            self.last_cpu_times = {
                "user": total_user,
                "system": total_system,
                "idle": 0
            }
            
            # Calculate percentage (rough estimate)
            total_delta = user_delta + system_delta
            cpu_percent = min(100.0, (total_delta / self.refresh_rate) * 10)  # Adjust multiplier as needed
            
            return cpu_percent, []
            
        except Exception:
            return 0.0, []
    
    def _get_cpu_info_from_proc(self) -> Dict:
        """Get CPU info from /proc/cpuinfo"""
        cpu_count = 0
        cpu_model = "Unknown"
        
        try:
            with open('/proc/cpuinfo', 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith('processor'):
                        cpu_count += 1
                    elif 'Hardware' in line and cpu_model == "Unknown":
                        cpu_model = line.split(':')[1].strip()
                    elif 'model name' in line and cpu_model == "Unknown":
                        cpu_model = line.split(':')[1].strip()
        except Exception:
            pass
        
        return {
            "count": cpu_count if cpu_count > 0 else os.cpu_count() or 1,
            "model": cpu_model
        }
    
    def _get_cpu_freq(self) -> Dict:
        """Get CPU frequency from sysfs for all cores"""
        freqs = []
        try:
            cpu_count = os.cpu_count() or 1
            for i in range(cpu_count):
                freq_path = f'/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq'
                if os.path.exists(freq_path):
                    with open(freq_path, 'r') as f:
                        freq = int(f.read().strip()) / 1000  # kHz to MHz
                        freqs.append(freq)
        except Exception:
            pass
        
        return {
            "freqs": freqs,
            "avg": sum(freqs) / len(freqs) if freqs else 0,
            "max_freq": max(freqs) if freqs else 0
        }
    
    def _get_termux_battery(self) -> Dict:
        """Get battery information from termux-battery-status"""
        data = self._safe_cmd(["termux-battery-status"], parse_json=True)
        if data:
            percentage = data.get("percentage", 0)
            status = data.get("status", "Unknown")
            current = data.get("current", 0)  # in microamps, negative when discharging
            
            # Estimate time remaining (rough calculation)
            time_remaining = "N/A"
            if current != 0:
                # Assume typical battery capacity (you may need to adjust this)
                battery_capacity_mah = 4000  # Adjust based on your device
                
                if "CHARGING" in status.upper() and current > 0:
                    remaining_capacity = battery_capacity_mah * (100 - percentage) / 100
                    hours_remaining = remaining_capacity / (current / 1000)
                    time_remaining = f"{int(hours_remaining)}h {int((hours_remaining % 1) * 60)}m"
                elif "DISCHARGING" in status.upper() and current < 0:
                    remaining_capacity = battery_capacity_mah * percentage / 100
                    hours_remaining = remaining_capacity / (abs(current) / 1000)
                    time_remaining = f"{int(hours_remaining)}h {int((hours_remaining % 1) * 60)}m"
            
            return {
                "percentage": percentage,
                "status": status,
                "health": data.get("health", "Unknown"),
                "temperature": data.get("temperature", 0),
                "plugged": data.get("plugged", "Unknown"),
                "current": current,
                "time_remaining": time_remaining
            }
        return {
            "percentage": 0, "status": "N/A", "health": "N/A",
            "temperature": 0, "plugged": "N/A", "current": 0,
            "time_remaining": "N/A"
        }
    
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
        try:
            net_io = psutil.net_io_counters()
            bytes_sent = net_io.bytes_sent
            bytes_recv = net_io.bytes_recv
            packets_sent = net_io.packets_sent
            packets_recv = net_io.packets_recv
            errin = net_io.errin
            errout = net_io.errout
            dropin = net_io.dropin
            dropout = net_io.dropout
        except Exception:
            bytes_sent = bytes_recv = packets_sent = packets_recv = 0
            errin = errout = dropin = dropout = 0
        
        # Get IP addresses
        ip_addr = "N/A"
        ip_addr_v6 = "N/A"
        try:
            addrs = psutil.net_if_addrs()
            if "wlan0" in addrs:
                for addr in addrs["wlan0"]:
                    if addr.family == 2:  # AF_INET (IPv4)
                        ip_addr = addr.address
                    elif addr.family == 10:  # AF_INET6 (IPv6)
                        ip_addr_v6 = addr.address
        except Exception:
            pass
        
        return {
            "ip": ip_addr,
            "ip_v6": ip_addr_v6,
            "bytes_sent": bytes_sent,
            "bytes_recv": bytes_recv,
            "packets_sent": packets_sent,
            "packets_recv": packets_recv,
            "errors_in": errin,
            "errors_out": errout,
            "drops_in": dropin,
            "drops_out": dropout
        }
    
    def _get_memory_info(self) -> Dict:
        """Get memory info"""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            return {
                "total": mem.total,
                "available": mem.available,
                "used": mem.used,
                "percent": mem.percent,
                "buffers": getattr(mem, 'buffers', 0),
                "cached": getattr(mem, 'cached', 0),
                "swap_total": swap.total,
                "swap_used": swap.used,
                "swap_percent": swap.percent
            }
        except Exception:
            return {
                "total": 1, "available": 0, "used": 0, "percent": 0,
                "buffers": 0, "cached": 0,
                "swap_total": 0, "swap_used": 0, "swap_percent": 0
            }
    
    def _collect_data(self):
        """Background thread to collect system data"""
        
        while self.running:
            try:
                # CPU data
                cpu_info = self._get_cpu_info_from_proc()
                cpu_usage, per_core = self._get_cpu_usage_from_times()
                cpu_freq_info = self._get_cpu_freq()
                
                with self.data_lock:
                    self.system_data["cpu"] = {
                        "percent": cpu_usage,
                        "per_core": per_core,
                        "count": cpu_info["count"],
                        "model": cpu_info["model"],
                        "freqs": cpu_freq_info.get("freqs", []),
                        "freq_avg": cpu_freq_info.get("avg", 0),
                        "freq_max": cpu_freq_info.get("max_freq", 0)
                    }
                    
                    # Memory data
                    self.system_data["memory"] = self._get_memory_info()
                    
                    # Storage data
                    try:
                        storage = psutil.disk_usage("/data")
                        self.system_data["storage"] = {
                            "total": storage.total,
                            "used": storage.used,
                            "free": storage.free,
                            "percent": storage.percent
                        }
                    except Exception:
                        self.system_data["storage"] = {
                            "total": 1, "used": 0, "free": 1, "percent": 0
                        }
                    
                    # Battery data
                    self.system_data["battery"] = self._get_termux_battery()
                    
                    # Network data with speed calculation
                    net_info = self._get_network_info()
                    current_time = time.time()
                    time_diff = current_time - self.last_net_io["time"]
                    
                    if time_diff > 0:
                        net_info["speed_up"] = (net_info["bytes_sent"] - self.last_net_io["sent"]) / time_diff
                        net_info["speed_down"] = (net_info["bytes_recv"] - self.last_net_io["recv"]) / time_diff
                    else:
                        net_info["speed_up"] = 0
                        net_info["speed_down"] = 0
                    
                    self.last_net_io = {
                        "sent": net_info["bytes_sent"],
                        "recv": net_info["bytes_recv"],
                        "time": current_time
                    }
                    self.system_data["network"] = net_info
                    
                    # Device info (static)
                    if not self.system_data["device"]:
                        self.system_data["device"] = self._get_device_info()
                    
                    # Process data
                    procs = []
                    try:
                        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                            try:
                                pinfo = proc.info
                                procs.append(pinfo)
                            except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
                                pass
                        
                        procs.sort(key=lambda x: x.get('cpu_percent', 0) or 0, reverse=True)
                    except Exception:
                        pass
                    
                    self.system_data["processes"] = procs[:15]
                
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
    
    def _create_bar(self, percentage: float, width: int = 20, show_percent: bool = True) -> Text:
        """Create a visual progress bar with actual colors"""
        filled = int(width * percentage / 100)
        empty = width - filled
        
        # Determine color
        if percentage >= 90:
            color = "red"
        elif percentage >= 70:
            color = "yellow"
        else:
            color = "green"
        
        bar = Text()
        bar.append("█" * filled, style=color)
        bar.append("░" * empty, style="dim")
        
        if show_percent:
            bar.append(f" {percentage:.1f}%", style="white")
        
        return bar
    
    def _make_header(self) -> Panel:
        """Create header"""
        current_time = datetime.now().strftime("%H:%M:%S")
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Get uptime
        uptime_str = "N/A"
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.read().split()[0])
                days = int(uptime_seconds // 86400)
                hours = int((uptime_seconds % 86400) // 3600)
                minutes = int((uptime_seconds % 3600) // 60)
                if days > 0:
                    uptime_str = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    uptime_str = f"{hours}h {minutes}m"
                else:
                    uptime_str = f"{minutes}m"
        except Exception:
            pass
        
        header_text = Text()
        header_text.append("🚀 ", style="bold magenta")
        header_text.append("Termux Monitor", style="bold cyan")
        header_text.append("  │  ", style="dim")
        header_text.append(f"📅 {current_date}", style="blue")
        header_text.append("  ", style="dim")
        header_text.append(f"🕐 {current_time}", style="green")
        header_text.append("  │  ", style="dim")
        header_text.append(f"⏱  {uptime_str}", style="yellow")
        
        return Panel(
            Align.center(header_text),
            box=box.ROUNDED,
            style="cyan",
            padding=(0, 1)
        )
    
    def _make_sidebar(self) -> Panel:
        """Create sidebar with icon tabs"""
        tabs_text = Text()
        
        for i, (icon, name) in enumerate(self.tabs):
            if i == self.selected_tab:
                tabs_text.append(f" {icon} ", style="bold white on blue")
            else:
                tabs_text.append(f" {icon} ", style="dim")
            tabs_text.append("\n\n")
        
        tabs_text.append("\n")
        tabs_text.append("↑↓ ", style="dim cyan")
        tabs_text.append("q", style="dim red")
        
        return Panel(
            Align.center(tabs_text),
            box=box.ROUNDED,
            style="blue",
            padding=(0, 0)
        )
    
    def _make_overview_panel(self) -> Panel:
        """Create overview panel"""
        with self.data_lock:
            data = self.system_data.copy()
        
        # Create grid layout
        grid = Table.grid(padding=(0, 2))
        grid.add_column(justify="left")
        grid.add_column(justify="left")
        
        # Row 1: CPU and Memory
        cpu_pct = data["cpu"].get("percent", 0)
        cpu_text = Text()
        cpu_text.append("💻 CPU\n", style="bold cyan")
        cpu_text.append(self._create_bar(cpu_pct, width=25))
        
        mem_pct = data["memory"].get("percent", 0)
        mem_text = Text()
        mem_text.append("🧠 Memory\n", style="bold cyan")
        mem_text.append(self._create_bar(mem_pct, width=25))
        
        grid.add_row(cpu_text, mem_text)
        grid.add_row("", "")
        
        # Row 2: Storage and Battery
        stor_pct = data["storage"].get("percent", 0)
        stor_text = Text()
        stor_text.append("💾 Storage\n", style="bold cyan")
        stor_text.append(self._create_bar(stor_pct, width=25))
        
        bat_pct = data["battery"].get("percentage", 0)
        bat_text = Text()
        bat_text.append("🔋 Battery\n", style="bold cyan")
        bat_text.append(self._create_bar(bat_pct, width=25))
        
        grid.add_row(stor_text, bat_text)
        grid.add_row("", "")
        
        # Network info
        net_text = Text()
        net_text.append("🌐 Network\n", style="bold cyan")
        net_text.append(f"↑ {self._format_speed(data['network'].get('speed_up', 0))}  ", style="green")
        net_text.append(f"↓ {self._format_speed(data['network'].get('speed_down', 0))}", style="blue")
        
        # Device info
        device = data["device"]
        device_text = Text()
        device_text.append("📱 Device\n", style="bold cyan")
        device_text.append(f"{device.get('manufacturer', '')} {device.get('model', '')}\n", style="white")
        device_text.append(f"Android {device.get('android', '')} • {device.get('arch', '')}", style="dim")
        
        grid.add_row(net_text, device_text)
        
        # Detailed stats table
        stats = Table(show_header=False, box=None, padding=(0, 1))
        stats.add_column("Label", style="dim", width=15)
        stats.add_column("Value", style="white")
        stats.add_column("Label2", style="dim", width=15)
        stats.add_column("Value2", style="white")
        
        stats.add_row(
            "CPU Cores", str(data["cpu"].get("count", 0)),
            "Memory Total", self._format_bytes(data["memory"].get("total", 0))
        )
        stats.add_row(
            "CPU Freq", f"{data['cpu'].get('freq_avg', 0):.0f} MHz",
            "Memory Used", self._format_bytes(data["memory"].get("used", 0))
        )
        stats.add_row(
            "Storage Total", self._format_bytes(data["storage"].get("total", 0)),
            "Storage Free", self._format_bytes(data["storage"].get("free", 0))
        )
        stats.add_row(
            "IP Address", data["network"].get("ip", "N/A"),
            "Battery Status", data["battery"].get("status", "N/A")
        )
        
        # Combine everything
        content = Table.grid()
        content.add_row(grid)
        content.add_row("")
        content.add_row(stats)
        
        return Panel(
            content,
            title="[bold cyan]📊 System Overview[/bold cyan]",
            box=box.ROUNDED,
            border_style="cyan"
        )
    
    def _make_cpu_panel(self) -> Panel:
        """Create CPU panel"""
        with self.data_lock:
            cpu_data = self.system_data["cpu"].copy()
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", style="white")
        
        usage = cpu_data.get("percent", 0)
        table.add_row("💻 Usage", "")
        table.add_row("", self._create_bar(usage, width=40))
        table.add_row("", "")
        
        table.add_row("🔢 Cores", str(cpu_data.get("count", 0)))
        table.add_row("🏗️  Model", cpu_data.get("model", "Unknown")[:50])
        
        freq_avg = cpu_data.get("freq_avg", 0)
        if freq_avg > 0:
            table.add_row("⚡ Avg Frequency", f"{freq_avg:.0f} MHz")
        
        freq_max = cpu_data.get("freq_max", 0)
        if freq_max > 0:
            table.add_row("📊 Max Frequency", f"{freq_max:.0f} MHz")
        
        # Show per-core frequencies if available
        freqs = cpu_data.get("freqs", [])
        if freqs:
            table.add_row("", "")
            table.add_row("⚙️  Core Frequencies", "")
            for i, freq in enumerate(freqs[:8]):  # Show max 8 cores
                table.add_row(f"   Core {i}", f"{freq:.0f} MHz")
        
        return Panel(
            table,
            title="[bold cyan]💻 CPU Details[/bold cyan]",
            box=box.ROUNDED,
            border_style="cyan"
        )
    
    def _make_memory_panel(self) -> Panel:
        """Create memory panel"""
        with self.data_lock:
            mem_data = self.system_data["memory"].copy()
        
        # Main stats
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Type", style="cyan", width=15)
        table.add_column("Details", style="white")
        
        # RAM
        table.add_row("🧠 RAM", "")
        table.add_row(
            "   Used",
            f"{self._format_bytes(mem_data.get('used', 0))} / {self._format_bytes(mem_data.get('total', 1))}"
        )
        table.add_row("", self._create_bar(mem_data.get("percent", 0), width=40))
        table.add_row("   Available", self._format_bytes(mem_data.get("available", 0)))
        
        cached = mem_data.get("cached", 0)
        if cached > 0:
            table.add_row("   Cached", self._format_bytes(cached))
        
        buffers = mem_data.get("buffers", 0)
        if buffers > 0:
            table.add_row("   Buffers", self._format_bytes(buffers))
        
        table.add_row("", "")
        
        # Swap
        swap_total = mem_data.get("swap_total", 0)
        if swap_total > 0:
            table.add_row("💿 Swap", "")
            table.add_row(
                "   Used",
                f"{self._format_bytes(mem_data.get('swap_used', 0))} / {self._format_bytes(swap_total)}"
            )
            table.add_row("", self._create_bar(mem_data.get("swap_percent", 0), width=40))
        else:
            table.add_row("💿 Swap", "Not configured")
        
        return Panel(
            table,
            title="[bold cyan]🧠 Memory Details[/bold cyan]",
            box=box.ROUNDED,
            border_style="cyan"
        )
    
    def _make_storage_panel(self) -> Panel:
        """Create storage panel with file explorer"""
        if not self.file_explorer.focused:
            # Show storage stats
            with self.data_lock:
                stor_data = self.system_data["storage"].copy()
            
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("Metric", style="cyan", width=20)
            table.add_column("Value", style="white")
            
            table.add_row("💾 Total Space", self._format_bytes(stor_data.get("total", 0)))
            table.add_row("📊 Used Space", self._format_bytes(stor_data.get("used", 0)))
            table.add_row("📂 Free Space", self._format_bytes(stor_data.get("free", 0)))
            table.add_row("", "")
            table.add_row("", self._create_bar(stor_data.get("percent", 0), width=40))
            table.add_row("", "")
            table.add_row("", "")
            table.add_row("💡 Tip", "Press Enter to browse files", style="dim italic")
            
            return Panel(
                table,
                title="[bold cyan]💾 Storage Details[/bold cyan]",
                box=box.ROUNDED,
                border_style="cyan"
            )
        else:
            # Show file explorer
            table = Table(show_header=True, box=box.SIMPLE, padding=(0, 1))
            table.add_column("", width=3, style="white")
            table.add_column("Name", style="white", overflow="fold")
            table.add_column("Size/Items", style="dim", justify="right", width=12)
            
            items = self.file_explorer.get_display_items(max_items=18)
            for i, (icon, name, path, is_dir, size, count) in enumerate(items):
                actual_index = self.file_explorer.scroll_offset + i
                marker = "▶" if actual_index == self.file_explorer.selected_index else " "
                
                if is_dir:
                    size_str = f"{count} items" if name != ".." else ""
                    style = "bold blue" if actual_index == self.file_explorer.selected_index else "blue"
                else:
                    size_str = self._format_bytes(size)
                    style = "bold white" if actual_index == self.file_explorer.selected_index else "white"
                
                table.add_row(marker, f"{icon} {name[:40]}", size_str, style=style)
            
            path_text = Text()
            path_text.append(f"📁 {self.file_explorer.current_path}\n", style="bold cyan")
            path_text.append("↑↓: Navigate  Enter: Open  Esc: Back  q: Quit", style="dim italic")
            
            content = Table.grid()
            content.add_row(path_text)
            content.add_row("")
            content.add_row(table)
            
            return Panel(
                content,
                title="[bold cyan]📂 File Explorer[/bold cyan]",
                box=box.ROUNDED,
                border_style="cyan"
            )
    
    def _make_battery_panel(self) -> Panel:
        """Create battery panel"""
        with self.data_lock:
            bat_data = self.system_data["battery"].copy()
        
        percentage = bat_data.get("percentage", 0)
        status = bat_data.get("status", "N/A")
        
        # Icon and color
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
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", style="white")
        
        table.add_row(f"{icon} Charge Level", f"[{color}]{percentage}%[/{color}]")
        table.add_row("", self._create_bar(percentage, width=40, show_percent=False))
        table.add_row("", "")
        
        table.add_row("⚙️  Status", status)
        table.add_row("💚 Health", bat_data.get("health", "N/A"))
        table.add_row("🌡️  Temperature", f"{bat_data.get('temperature', 0):.1f}°C")
        table.add_row("🔌 Plugged", bat_data.get("plugged", "N/A"))
        
        current = bat_data.get("current", 0)
        if current != 0:
            table.add_row("⚡ Current", f"{current} µA")
        
        time_remaining = bat_data.get("time_remaining", "N/A")
        if time_remaining != "N/A":
            if "CHARGING" in status.upper():
                table.add_row("⏱️  Time to Full", time_remaining)
            elif "DISCHARGING" in status.upper():
                table.add_row("⏱️  Time Remaining", time_remaining)
        
        return Panel(
            table,
            title="[bold cyan]🔋 Battery Details[/bold cyan]",
            box=box.ROUNDED,
            border_style="cyan"
        )
    
    def _make_network_panel(self) -> Panel:
        """Create network panel"""
        with self.data_lock:
            net_data = self.system_data["network"].copy()
        
        # Speed section
        speed_table = Table(show_header=False, box=None, padding=(0, 2))
        speed_table.add_column("Direction", style="cyan", width=20)
        speed_table.add_column("Speed", style="white")
        
        speed_table.add_row("📤 Upload Speed", f"[green]{self._format_speed(net_data.get('speed_up', 0))}[/green]")
        speed_table.add_row("📥 Download Speed", f"[blue]{self._format_speed(net_data.get('speed_down', 0))}[/blue]")
        
        # Stats section
        stats_table = Table(show_header=False, box=None, padding=(0, 2))
        stats_table.add_column("Metric", style="cyan", width=20)
        stats_table.add_column("Value", style="white")
        
        stats_table.add_row("", "")
        stats_table.add_row("🌐 IP Address (v4)", net_data.get("ip", "N/A"))
        stats_table.add_row("🌐 IP Address (v6)", net_data.get("ip_v6", "N/A")[:40])
        stats_table.add_row("", "")
        stats_table.add_row("📊 Total Sent", self._format_bytes(net_data.get("bytes_sent", 0)))
        stats_table.add_row("📊 Total Received", self._format_bytes(net_data.get("bytes_recv", 0)))
        stats_table.add_row("", "")
        stats_table.add_row("📦 Packets Sent", f"{net_data.get('packets_sent', 0):,}")
        stats_table.add_row("📦 Packets Received", f"{net_data.get('packets_recv', 0):,}")
        
        errors_in = net_data.get("errors_in", 0)
        errors_out = net_data.get("errors_out", 0)
        if errors_in > 0 or errors_out > 0:
            stats_table.add_row("", "")
            stats_table.add_row("⚠️  Errors In", str(errors_in))
            stats_table.add_row("⚠️  Errors Out", str(errors_out))
        
        # Combine
        content = Table.grid()
        content.add_row(speed_table)
        content.add_row(stats_table)
        
        return Panel(
            content,
            title="[bold cyan]🌐 Network Details[/bold cyan]",
            box=box.ROUNDED,
            border_style="cyan"
        )
    
    def _make_processes_panel(self) -> Panel:
        """Create processes panel"""
        with self.data_lock:
            procs = self.system_data["processes"][:12]
        
        table = Table(show_header=True, box=box.SIMPLE)
        table.add_column("PID", style="cyan", justify="right", width=8)
        table.add_column("Name", style="white", width=25, overflow="fold")
        table.add_column("CPU%", style="yellow", justify="right", width=8)
        table.add_column("MEM%", style="green", justify="right", width=8)
        table.add_column("Status", style="dim", width=10)
        
        for proc in procs:
            cpu_pct = proc.get('cpu_percent') or 0
            mem_pct = proc.get('memory_percent') or 0
            
            table.add_row(
                str(proc.get('pid', '')),
                proc.get('name', 'N/A')[:23],
                f"{cpu_pct:.1f}",
                f"{mem_pct:.1f}",
                proc.get('status', 'N/A')[:8]
            )
        
        if not procs:
            table.add_row("—", "No data available", "—", "—", "—")
        
        return Panel(
            table,
            title="[bold cyan]⚙️  Top Processes[/bold cyan]",
            box=box.ROUNDED,
            border_style="cyan"
        )
    
    def _get_content_panel(self) -> Panel:
        """Get content based on selected tab"""
        _, tab_name = self.tabs[self.selected_tab]
        
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
        """Create layout with fixed dimensions"""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
        )
        
        layout["body"].split_row(
            Layout(name="sidebar", size=self.sidebar_width),
            Layout(name="content"),
        )
        
        layout["header"].update(self._make_header())
        layout["sidebar"].update(self._make_sidebar())
        layout["content"].update(self._get_content_panel())
        
        return layout
    
    def _handle_input(self):
        """Handle keyboard input"""
        import termios
        import tty
        import select
        
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())
            
            if select.select([sys.stdin], [], [], 0)[0]:
                char = sys.stdin.read(1)
                
                if char == '\x1b':  # ESC sequence
                    # Try to read more characters (for arrow keys)
                    old_flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
                    fcntl.fcntl(sys.stdin, fcntl.F_SETFL, old_flags | os.O_NONBLOCK)
                    
                    try:
                        additional = sys.stdin.read(2)
                        char += additional
                    except:
                        # No additional characters, it's ESC alone
                        if self.file_explorer.focused:
                            self.file_explorer.focused = False
                            return
                    finally:
                        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, old_flags)
                    
                    if self.file_explorer.focused:
                        if char == '\x1b[A':  # Up
                            self.file_explorer.navigate_up()
                        elif char == '\x1b[B':  # Down
                            self.file_explorer.navigate_down()
                        elif char == '\x1b':  # ESC alone
                            self.file_explorer.focused = False
                    else:
                        if char == '\x1b[A':  # Up
                            self.selected_tab = (self.selected_tab - 1) % len(self.tabs)
                        elif char == '\x1b[B':  # Down
                            self.selected_tab = (self.selected_tab + 1) % len(self.tabs)
                
                elif char == '\r' or char == '\n':  # Enter
                    if self.tabs[self.selected_tab][1] == "Storage":
                        if self.file_explorer.focused:
                            self.file_explorer.enter_item()
                        else:
                            self.file_explorer.focused = True
                
                elif char.lower() == 'q':
                    self.running = False
                    
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    
    def run(self):
        """Main run loop"""
        try:
            with Live(
                self._create_layout(),
                console=self.console,
                refresh_per_second=4,
                screen=False  # Don't use alternate screen to keep fixed height
            ) as live:
                while self.running:
                    self._handle_input()
                    live.update(self._create_layout())
                    time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            self.console.print("\n[green]✨ Monitor closed![/green]")


def main():
    """Entry point"""
    try:
        monitor = TermuxMonitor()
        monitor.run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()