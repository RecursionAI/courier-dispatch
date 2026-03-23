#!/usr/bin/env bash
set -euo pipefail

# Courier Agent — Install Helper
# Installs the package and configures Claude Desktop

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Courier Agent Installer${NC}"
echo "========================"
echo

# 1. Check Python
if ! command -v python3 &>/dev/null; then
    echo -e "${YELLOW}Error: Python 3 is required but not found.${NC}"
    exit 1
fi

# 2. Install the package
echo "Installing courier-agent..."
if pip install courier-agent 2>/dev/null; then
    echo -e "${GREEN}✓ courier-agent installed${NC}"
elif pip install -e . 2>/dev/null; then
    echo -e "${GREEN}✓ courier-agent installed (development mode)${NC}"
else
    echo -e "${YELLOW}Warning: Could not install courier-agent. Install manually with: pip install courier-agent${NC}"
fi

# 3. Detect Claude Desktop config location
case "$(uname -s)" in
    Darwin)
        CONFIG_DIR="$HOME/Library/Application Support/Claude"
        ;;
    Linux)
        CONFIG_DIR="$HOME/.config/Claude"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        CONFIG_DIR="$APPDATA/Claude"
        ;;
    *)
        echo -e "${YELLOW}Unsupported OS. Please configure Claude Desktop manually.${NC}"
        CONFIG_DIR=""
        ;;
esac

CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"

# 4. Get project path
echo
read -rp "Enter your project path (or press Enter for current directory): " PROJECT_PATH
PROJECT_PATH="${PROJECT_PATH:-$(pwd)}"
PROJECT_PATH="$(cd "$PROJECT_PATH" && pwd)"  # Resolve to absolute path

echo -e "Project path: ${GREEN}$PROJECT_PATH${NC}"

# 5. Update Claude Desktop config
if [ -n "$CONFIG_DIR" ]; then
    mkdir -p "$CONFIG_DIR"

    if [ -f "$CONFIG_FILE" ]; then
        # Merge into existing config using Python
        python3 -c "
import json, sys

config_file = '$CONFIG_FILE'
project_path = '$PROJECT_PATH'

with open(config_file) as f:
    config = json.load(f)

config.setdefault('mcpServers', {})
config['mcpServers']['courier-agent'] = {
    'command': 'courier-agent',
    'args': [project_path]
}

with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)

print('Updated existing config')
"
    else
        # Create new config
        python3 -c "
import json

config = {
    'mcpServers': {
        'courier-agent': {
            'command': 'courier-agent',
            'args': ['$PROJECT_PATH']
        }
    }
}

with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)

print('Created new config')
"
    fi
    echo -e "${GREEN}✓ Claude Desktop config updated${NC}"
fi

# 6. Copy SKILL.md
SKILL_DIR="$HOME/.claude/skills/courier-agent"
mkdir -p "$SKILL_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SOURCE="$SCRIPT_DIR/../skill/courier-agent/SKILL.md"

if [ -f "$SKILL_SOURCE" ]; then
    cp "$SKILL_SOURCE" "$SKILL_DIR/SKILL.md"
    echo -e "${GREEN}✓ SKILL.md installed to $SKILL_DIR${NC}"
else
    echo -e "${YELLOW}Warning: SKILL.md not found at $SKILL_SOURCE${NC}"
fi

# 7. Summary
echo
echo -e "${GREEN}Installation complete!${NC}"
echo
echo "Next steps:"
echo "  1. Restart Claude Desktop"
echo "  2. Open a conversation and say 'guide me' to activate Courier Agent"
echo

# Check for optional dependencies
if ! command -v bd &>/dev/null; then
    echo -e "${YELLOW}Optional: Install Beads for task planning:${NC}"
    echo "  curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash"
    echo
fi

if ! command -v rg &>/dev/null; then
    echo -e "${YELLOW}Optional: Install ripgrep for faster code search:${NC}"
    echo "  brew install ripgrep  (macOS)"
    echo "  apt install ripgrep   (Linux)"
    echo
fi
