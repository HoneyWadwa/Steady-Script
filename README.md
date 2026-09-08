# Steady-Script Flask Review 1
This is the working Flask + SQLite dashboard prototype for Review 1.

## Run
1. Install Python 3.10+
2. In this folder run: `python -m venv venv`
3. Activate it.
4. Run: `pip install -r requirements.txt`
5. Run: `python app.py`
6. Open `http://127.0.0.1:5000`

## Review demonstration
Click **Run Demo Session**. This creates session, stroke and event records in SQLite and displays them on the dashboard. Then open Sessions and Calibration.

## Future IoT integration
The ESP32/BLE gateway will POST processed telemetry to `POST /api/ingest`.

Example:
`{"session_id":1,"stroke_amp":0.74,"speed":0.82,"pressure":0.61,"distance_mm":3.2,"freeze":0,"cue":1,"stroke_duration_ms":430}`

## Architecture
ESP32 sensors -> edge processing -> BLE gateway -> Flask /api/ingest -> SQLite -> dashboard.

This prototype does not diagnose Parkinson's disease. A freeze-like event is an engineering low-motion event and the writing-quality score is project-specific.
