#!/data/data/com.termux/files/usr/bin/bash

# Config
UPDATE_INTERVAL=0.25
BAR_FULL="█"
BAR_EMPTY="░"
BAR_LEN=15
TAB_NAMES=("Overview" "Memory" "Battery" "Storage" "CPU")
TAB_COUNT=${#TAB_NAMES[@]}
SELECTED_TAB=0
TAB_WIDTH=14
PANEL_OFFSET=3
UI_WIDTH=85
UI_HEIGHT=20

# Colors
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_DIM="\033[2m"
C_CYAN="\033[36m"
C_GREEN="\033[32m"
C_YELLOW="\033[33m"
C_RED="\033[31m"
C_BLUE="\033[34m"
C_MAGENTA="\033[35m"

# Terminal setup
setup_terminal() {
    stty -echo -icanon time 0 min 0
    tput civis  # Hide cursor
    tput smcup  # Save screen and use alternate buffer
    clear
}

# Cleanup on exit
cleanup() {
    tput cnorm  # Show cursor
    tput rmcup  # Restore screen
    stty sane
    clear
    exit 0
}

trap cleanup EXIT INT TERM

# Safe execution
safe_cmd() { "$@" 2>/dev/null || echo "N/A"; }

to_int() { printf "%.0f" "$1" 2>/dev/null || echo 0; }

hr() {
    local b=${1:-0}
    if [[ $b == "N/A" ]]; then echo "N/A"; return; fi
    if ((b<1024)); then echo "${b}B"
    elif ((b<1048576)); then printf "%.1fK" "$(echo "$b/1024" | bc -l)"
    elif ((b<1073741824)); then printf "%.1fM" "$(echo "$b/1048576" | bc -l)"
    else printf "%.1fG" "$(echo "$b/1073741824" | bc -l)"; fi
}

bar() {
    local cur=$(to_int "$1")
    local max=$(to_int "$2")
    local len=$BAR_LEN
    [[ $max -eq 0 ]] && max=1
    ((cur>max)) && cur=$max
    local filled=$(( cur * len / max ))
    local empty=$(( len - filled ))
    
    local color=""
    local pct=$((cur * 100 / max))
    if ((pct >= 90)); then color="$C_RED"
    elif ((pct >= 70)); then color="$C_YELLOW"
    else color="$C_GREEN"; fi
    
    echo -ne "${color}"
    printf "%0.s$BAR_FULL" $(seq 1 $filled)
    echo -ne "${C_DIM}"
    printf "%0.s$BAR_EMPTY" $(seq 1 $empty)
    echo -ne "${C_RESET}"
}

# Read keys for tab navigation
handle_input() {
    local key
    key=$(dd bs=1 count=1 2>/dev/null)
    if [[ $key == $'\x1b' ]]; then
        read -rsn2 key
        if [[ $key == "[A" ]]; then 
            ((SELECTED_TAB--))
            ((SELECTED_TAB<0)) && SELECTED_TAB=$((TAB_COUNT-1))
            return 0
        elif [[ $key == "[B" ]]; then 
            ((SELECTED_TAB++))
            ((SELECTED_TAB>=TAB_COUNT)) && SELECTED_TAB=0
            return 0
        fi
    elif [[ $key == "q" || $key == "Q" ]]; then
        cleanup
    fi
    return 1
}

# Draw box with modern borders
draw_box() {
    local row=$1
    local col=$2
    local width=$3
    local height=$4
    local title=$5
    
    # Top border
    tput cup $row $col
    echo -ne "${C_CYAN}╭"
    if [[ -n $title ]]; then
        echo -ne "─${C_BOLD} $title ${C_RESET}${C_CYAN}"
        printf "─%.0s" $(seq 1 $((width - ${#title} - 5)))
    else
        printf "─%.0s" $(seq 1 $((width - 2)))
    fi
    echo -ne "╮${C_RESET}"
    
    # Sides
    for ((i=1; i<height-1; i++)); do
        tput cup $((row + i)) $col
        echo -ne "${C_CYAN}│${C_RESET}"
        tput cup $((row + i)) $((col + width - 1))
        echo -ne "${C_CYAN}│${C_RESET}"
    done
    
    # Bottom border
    tput cup $((row + height - 1)) $col
    echo -ne "${C_CYAN}╰"
    printf "─%.0s" $(seq 1 $((width - 2)))
    echo -ne "╯${C_RESET}"
}

# Render static layout - only called once
render_static() {
    clear
    
    # Main panel
    draw_box 0 0 $((UI_WIDTH - TAB_WIDTH - 2)) $UI_HEIGHT "Termux System Monitor"
    
    # Tabs panel
    draw_box 0 $((UI_WIDTH - TAB_WIDTH - 1)) $TAB_WIDTH $UI_HEIGHT "Tabs"
    
    # Static labels
    tput cup 2 $PANEL_OFFSET
    echo -ne "${C_BOLD}🕒 Time & Uptime${C_RESET}"
    
    tput cup 5 $PANEL_OFFSET
    echo -ne "${C_BOLD}💻 CPU Info${C_RESET}"
    
    tput cup 8 $PANEL_OFFSET
    echo -ne "${C_BOLD}🧠 Memory & Swap${C_RESET}"
    
    tput cup 11 $PANEL_OFFSET
    echo -ne "${C_BOLD}💾 Storage${C_RESET}"
    
    tput cup 14 $PANEL_OFFSET
    echo -ne "${C_BOLD}🔋 Battery${C_RESET}"
    
    tput cup 17 $PANEL_OFFSET
    echo -ne "${C_BOLD}📱 Device Info${C_RESET}"
    
    # Help text
    tput cup $((UI_HEIGHT - 1)) $PANEL_OFFSET
    echo -ne "${C_DIM}↑/↓: Navigate tabs | q: Quit${C_RESET}"
}

# Clear line helper
clear_line() {
    local row=$1
    local col=$2
    local width=$3
    tput cup $row $col
    printf "%${width}s" ""
}

# Update dynamic values - only updates changed content
update_values() {
    local PANEL_WIDTH=$((UI_WIDTH - TAB_WIDTH - 2 - PANEL_OFFSET - 2))
    
    # Fetch dynamic data
    NOW=$(date +"%Y-%m-%d %H:%M:%S")
    UPTIME=$(uptime -p 2>/dev/null || echo "N/A")
    CPU_ARCH=$(safe_cmd getprop ro.product.cpu.abi)
    CPU_MODEL=$(safe_cmd cat /proc/cpuinfo | grep 'model name' | head -n1 | cut -d':' -f2 | xargs)
    [[ -z "$CPU_MODEL" ]] && CPU_MODEL=$(safe_cmd cat /proc/cpuinfo | grep 'Hardware' | head -n1 | cut -d':' -f2 | xargs)
    CPU_USAGE=$(safe_cmd top -bn1 | awk '/CPU:/ {gsub("%",""); print int($2+$4+$6)}' || echo 0)
    
    MEM_INFO=$(free 2>/dev/null | awk '/Mem:/ {print $2,$3}')
    read -r MEM_TOTAL MEM_USED <<< "$MEM_INFO"
    [[ -z "$MEM_TOTAL" ]] && MEM_TOTAL=1
    [[ -z "$MEM_USED" ]] && MEM_USED=0
    
    SWAP_INFO=$(free 2>/dev/null | awk '/Swap:/ {print $2,$3}')
    read -r SWAP_TOTAL SWAP_USED <<< "$SWAP_INFO"
    [[ -z "$SWAP_TOTAL" ]] && SWAP_TOTAL=0
    [[ -z "$SWAP_USED" ]] && SWAP_USED=0
    
    STORAGE_INFO=$(df /data 2>/dev/null | awk 'NR==2 {print $2,$3}')
    read -r STORAGE_TOTAL STORAGE_USED <<< "$STORAGE_INFO"
    [[ -z "$STORAGE_TOTAL" ]] && STORAGE_TOTAL=1
    [[ -z "$STORAGE_USED" ]] && STORAGE_USED=0
    
    BAT_INFO=$(termux-battery-status 2>/dev/null | jq -r '.percentage,.status,.temperature,.health' 2>/dev/null)
    if [[ -n "$BAT_INFO" ]]; then
        BAT_ARRAY=($BAT_INFO)
        BATTERY=${BAT_ARRAY[0]:-0}
        BAT_STATUS=${BAT_ARRAY[1]:-"N/A"}
        BAT_TEMP=${BAT_ARRAY[2]:-"N/A"}
        BAT_HEALTH=${BAT_ARRAY[3]:-"N/A"}
    else
        BATTERY=0
        BAT_STATUS="N/A"
        BAT_TEMP="N/A"
        BAT_HEALTH="N/A"
    fi
    
    IP_ADDR=$(safe_cmd ip addr show wlan0 | awk '/inet / {print $2}' | cut -d'/' -f1)
    [[ -z "$IP_ADDR" ]] && IP_ADDR="N/A"
    ANDROID=$(safe_cmd getprop ro.build.version.release)
    MODEL=$(safe_cmd getprop ro.product.model)

    CPU_BAR=$(bar $CPU_USAGE 100)
    MEM_BAR=$(bar $MEM_USED $MEM_TOTAL)
    SWAP_BAR=$(bar $SWAP_USED $SWAP_TOTAL)
    STORAGE_BAR=$(bar $STORAGE_USED $STORAGE_TOTAL)
    BAT_BAR=$(bar $BATTERY 100)

    # --- Update panel content ---
    # Time & Uptime
    clear_line 3 $PANEL_OFFSET $PANEL_WIDTH
    tput cup 3 $PANEL_OFFSET
    echo -ne "${C_GREEN}$NOW${C_RESET} ${C_DIM}│${C_RESET} ${C_YELLOW}$UPTIME${C_RESET}"
    
    # CPU Info
    clear_line 6 $PANEL_OFFSET $PANEL_WIDTH
    tput cup 6 $PANEL_OFFSET
    echo -ne "${C_DIM}Arch:${C_RESET} $CPU_ARCH ${C_DIM}│ Model:${C_RESET} ${CPU_MODEL:0:25}"
    
    clear_line 7 $PANEL_OFFSET $PANEL_WIDTH
    tput cup 7 $PANEL_OFFSET
    echo -ne "${C_DIM}Usage:${C_RESET} ${C_BOLD}$CPU_USAGE%${C_RESET} $CPU_BAR"
    
    # Memory & Swap
    clear_line 9 $PANEL_OFFSET $PANEL_WIDTH
    tput cup 9 $PANEL_OFFSET
    echo -ne "${C_DIM}Memory:${C_RESET} $(hr $MEM_USED) / $(hr $MEM_TOTAL)"
    tput cup 9 $((PANEL_OFFSET + 35))
    echo -ne "$MEM_BAR"
    
    clear_line 10 $PANEL_OFFSET $PANEL_WIDTH
    tput cup 10 $PANEL_OFFSET
    if [[ $SWAP_TOTAL -gt 0 ]]; then
        echo -ne "${C_DIM}Swap:${C_RESET}   $(hr $SWAP_USED) / $(hr $SWAP_TOTAL)"
        tput cup 10 $((PANEL_OFFSET + 35))
        echo -ne "$SWAP_BAR"
    else
        echo -ne "${C_DIM}Swap:${C_RESET}   Not configured"
    fi
    
    # Storage
    clear_line 12 $PANEL_OFFSET $PANEL_WIDTH
    tput cup 12 $PANEL_OFFSET
    echo -ne "${C_DIM}Used:${C_RESET} $(hr $((STORAGE_USED * 1024))) / $(hr $((STORAGE_TOTAL * 1024)))"
    tput cup 12 $((PANEL_OFFSET + 35))
    echo -ne "$STORAGE_BAR"
    
    # Battery
    clear_line 15 $PANEL_OFFSET $PANEL_WIDTH
    tput cup 15 $PANEL_OFFSET
    local bat_icon="🔋"
    [[ $BATTERY -lt 20 ]] && bat_icon="🪫"
    [[ "$BAT_STATUS" == "CHARGING" ]] && bat_icon="⚡"
    echo -ne "$bat_icon ${C_BOLD}$BATTERY%${C_RESET} ${C_DIM}│${C_RESET} $BAT_STATUS"
    
    clear_line 16 $PANEL_OFFSET $PANEL_WIDTH
    tput cup 16 $PANEL_OFFSET
    echo -ne "${C_DIM}Temp:${C_RESET} ${BAT_TEMP}°C ${C_DIM}│ Health:${C_RESET} $BAT_HEALTH"
    tput cup 16 $((PANEL_OFFSET + 35))
    echo -ne "$BAT_BAR"
    
    # Device Info
    clear_line 18 $PANEL_OFFSET $PANEL_WIDTH
    tput cup 18 $PANEL_OFFSET
    echo -ne "${C_DIM}Model:${C_RESET} $MODEL ${C_DIM}│ Android:${C_RESET} $ANDROID"
    
    clear_line 19 $PANEL_OFFSET $PANEL_WIDTH
    tput cup 19 $PANEL_OFFSET
    echo -ne "${C_DIM}IP:${C_RESET} $IP_ADDR"
}

# Update tabs highlight
update_tabs() {
    local tab_col=$((UI_WIDTH - TAB_WIDTH))
    
    for i in "${!TAB_NAMES[@]}"; do
        tput cup $((2 + i * 2)) $tab_col
        if [[ $i -eq $SELECTED_TAB ]]; then
            echo -ne " ${C_BOLD}${C_GREEN}▶ ${TAB_NAMES[i]}${C_RESET}  "
        else
            echo -ne "   ${C_DIM}${TAB_NAMES[i]}${C_RESET}  "
        fi
    done
}

# --- Main ---
setup_terminal
render_static
update_tabs

TAB_CHANGED=0
while true; do
    handle_input
    if [[ $? -eq 0 ]]; then
        TAB_CHANGED=1
    fi
    
    update_values
    
    if [[ $TAB_CHANGED -eq 1 ]]; then
        update_tabs
        TAB_CHANGED=0
    fi
    
    sleep $UPDATE_INTERVAL
done