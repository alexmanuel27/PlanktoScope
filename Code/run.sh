#!/bin/bash
# Script to launch PlanktoScope in simulation mode (without Raspberry Pi)

cd "$(dirname "$0")"

# Set simulation mode
export SIMULATION_MODE=true

# Launch application
echo "Launching PlanktoScope in SIMULATION mode"
echo "The application will be accessible at http://localhost:5000"
echo ""
./planktoscope-env/bin/python3 app.py
