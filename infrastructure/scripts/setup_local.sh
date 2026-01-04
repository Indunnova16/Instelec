#!/bin/bash
# =============================================================================
# Local Development Setup Script for TransMaint
# =============================================================================

set -e

echo "=========================================="
echo "TransMaint - Local Development Setup"
echo "=========================================="

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
if [ "$PYTHON_VERSION" != "3.12" ] && [ "$PYTHON_VERSION" != "3.11" ]; then
    echo "Warning: Python 3.11 or 3.12 recommended. Found: $PYTHON_VERSION"
fi

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements/local.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo "Creating .env file from example..."
    cp .env.example .env
    echo ""
    echo "!!! IMPORTANT: Please edit .env with your local settings !!!"
    echo ""
fi

# Check if PostgreSQL is available
if command -v psql &> /dev/null; then
    echo "PostgreSQL client found."
    # Try to create database if not exists
    if psql -lqt | cut -d \| -f 1 | grep -qw transmaint; then
        echo "Database 'transmaint' already exists."
    else
        echo "Creating database 'transmaint'..."
        createdb transmaint 2>/dev/null || echo "Could not create database. Please create it manually."
    fi
else
    echo "PostgreSQL client not found. Please install PostgreSQL."
    echo "On macOS: brew install postgresql"
    echo "On Ubuntu: sudo apt-get install postgresql postgresql-contrib"
fi

# Check if Redis is available
if command -v redis-cli &> /dev/null; then
    echo "Redis client found."
    if redis-cli ping &> /dev/null; then
        echo "Redis server is running."
    else
        echo "Redis server not running. Please start it:"
        echo "On macOS: brew services start redis"
        echo "On Ubuntu: sudo systemctl start redis"
    fi
else
    echo "Redis not found. Installing is recommended for Celery."
    echo "On macOS: brew install redis"
    echo "On Ubuntu: sudo apt-get install redis-server"
fi

# Run migrations
echo ""
echo "Running database migrations..."
python manage.py migrate --settings=config.settings.local

# Create superuser if needed
echo ""
echo "Do you want to create a superuser? (y/n)"
read -r CREATE_SUPERUSER
if [ "$CREATE_SUPERUSER" = "y" ]; then
    python manage.py createsuperuser --settings=config.settings.local
fi

# Load initial data
echo ""
echo "Do you want to load sample data? (y/n)"
read -r LOAD_DATA
if [ "$LOAD_DATA" = "y" ]; then
    python manage.py seed_data --settings=config.settings.local
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To start the development server:"
echo "  source venv/bin/activate"
echo "  python manage.py runserver"
echo ""
echo "To start Celery worker:"
echo "  celery -A config worker -l info"
echo ""
echo "To start Celery beat:"
echo "  celery -A config beat -l info"
echo ""
