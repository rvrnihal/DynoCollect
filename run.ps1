# PowerShell script to run both frontend and backend servers

# Create a function to start the backend server
function Start-Backend {
    Write-Host "Starting Flask backend server..."
    Start-Process powershell -ArgumentList "-Command", "cd '$PSScriptRoot'; python app/backend/app.py"
}

# Create a function to start the frontend server
function Start-Frontend {
    Write-Host "Starting Streamlit frontend server..."
    Start-Process powershell -ArgumentList "-Command", "cd '$PSScriptRoot'; streamlit run app/frontend/app.py"
}

# Main execution
Write-Host "Starting Data Collection App with Authentication..."

# Start the backend server
Start-Backend

# Wait a moment for the backend to initialize
Start-Sleep -Seconds 2

# Start the frontend server
Start-Frontend

Write-Host "Both servers are running!"
Write-Host "Backend: http://localhost:5000"
Write-Host "Frontend: http://localhost:8501"
Write-Host "Press Ctrl+C to stop the servers."

# Keep the script running
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host "Shutting down servers..."
}