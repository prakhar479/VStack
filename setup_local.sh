#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Setting up V-Stack local environment...${NC}"

# 1. Create Data Directories
echo -e "${GREEN}Creating data directories...${NC}"
mkdir -p data/metadata
mkdir -p data/storage1
mkdir -p data/storage2
mkdir -p data/storage3
mkdir -p data/uploads

# 2. Python Virtual Environment
echo -e "${GREEN}Setting up Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

source venv/bin/activate

# 3. Install Python Dependencies
echo -e "${GREEN}Installing Python dependencies...${NC}"
pip install --upgrade pip
pip install -r metadata-service/requirements.txt
pip install -r uploader/requirements.txt
pip install -r client/requirements.txt
pip install aiohttp aiofiles

# 4. Build Storage Node (Go)
echo -e "${GREEN}Building Storage Node binary...${NC}"
if command -v go &> /dev/null; then
    cd storage-node
    go build -o storage-node main.go
    cd ..
    echo "Storage node built successfully."
else
    echo "Error: Go is not installed. Please install Go to run storage nodes."
    exit 1
fi

echo -e "${BLUE}Setup complete!${NC}"
echo "You can now run the services using the instructions in LOCAL_RUN_GUIDE.md"
