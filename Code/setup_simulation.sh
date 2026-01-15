#!/bin/bash
# Script to setup PlanktoScope development environment in simulation mode

cd "$(dirname "$0")"

echo "Setting up PlanktoScope environment (simulation mode)"
echo "========================================================="
echo ""

# Remove old environment if it exists
if [ -d "planktoscope-env" ]; then
    echo "Removing old virtual environment..."
    rm -rf planktoscope-env
fi

# Create new virtual environment
echo "Creating new virtual environment..."
python3 -m venv planktoscope-env

if [ $? -ne 0 ]; then
    echo "Error creating virtual environment"
    echo "Install python3-venv with: sudo apt-get install python3-venv"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
./planktoscope-env/bin/pip install --upgrade pip
./planktoscope-env/bin/pip install -r requirements.txt

# Install opencv-python and numpy for image processing
echo "Installing image processing libraries..."
./planktoscope-env/bin/pip install opencv-python numpy

echo ""
echo "Setup completed!"
echo ""
echo "To launch the application in simulation mode:"
echo "  ./run_simulation.sh"
echo ""
echo "Or manually:"
echo "  SIMULATION_MODE=true ./planktoscope-env/bin/python3 app.py"
