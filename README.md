# Energy System Modelling

A Python project for energy system analysis and modelling.

## Prerequisites

- Python 3.11 or higher
- Git (for cloning the repository)

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/ajones-1/energy-system-modelling.git
cd energy-system-modelling
```

### 2. Install uv (Python Package Manager)

uv is a fast Python package manager and project manager written in Rust. Choose one of the installation methods below:

#### Windows (PowerShell)
```powershell
# Install using PowerShell (recommended)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### Alternative Windows Installation Methods
```powershell
# Using pip
pip install uv
```

#### macOS/Linux
```bash
# Using the installer script
curl -LsSf https://astral.sh/uv/install.sh | sh

# Using pip
pip install uv

# Using Homebrew (macOS)
brew install uv
```

### 3. Set Up Python Environment

The project uses Python 3.11. uv will automatically manage the Python version and virtual environment:

```bash
# Create and activate virtual environment with the correct Python version
uv venv

# Activate the virtual environment
# On Windows:
.venv\Scripts\activate

# On macOS/Linux:
source .venv/bin/activate
```

### 4. Install Dependencies

```bash
# Install project dependencies
uv pip install -e .

# Install additional development dependencies (if any)
# uv pip install -r requirements-dev.txt
```

### 5. Verify Installation

Run the main script to verify everything is working:

```bash
python src/main.py
```

## Project Structure

```
energy-system-modelling/
├── .venv/              # Virtual environment (created after setup)
├── data/               # Data files
├── results/            # Output results
├── src/                # Source code
├── pyproject.toml      # Project configuration
└── README.md           # This file
```

### Running the Project
```bash
# Ensure virtual environment is activated
.venv\Scripts\activate  # Windows
.venv/bin/activate      # macOS/Linux

# Or run other scripts
python src/main.py
```

### Deactivating the Environment
```bash
# When you're done working
deactivate
```

## Troubleshooting

### Common Issues

1. **Python version not found**: Ensure Python 3.11+ is installed on your system
2. **uv command not found**: Restart your terminal after installing uv, or add it to your PATH
3. **Permission errors on Windows**: Run PowerShell as Administrator if needed
4. **Virtual environment not activating**: Ensure you're in the project root directory

### Getting Help

- Check [uv documentation](https://docs.astral.sh/uv/) for uv-specific issues
- For Python environment issues, verify your Python installation with `python --version`