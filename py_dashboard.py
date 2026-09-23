import streamlit as st
import serial
import serial.tools.list_ports
import pandas as pd
import re
import time
from collections import deque

# --- CONFIGURATION ---
st.set_page_config(page_title="Smooth UART Dashboard", layout="wide")

if 'data_buffer' not in st.session_state:
    # Using Deques for performance
    st.session_state.data_buffer = {
        'X': deque([0.0] * 50, maxlen=50),
        'Y': deque([0.0] * 50, maxlen=50),
        'Z': deque([0.0] * 50, maxlen=50),
        'Similarity': deque([0.0] * 50, maxlen=50),
        'Current': deque([0.0] * 50, maxlen=50)
    }
if 'running' not in st.session_state:
    st.session_state.running = False

# --- SIDEBAR SETTINGS ---
st.sidebar.title("📡 UART Control")
ports = [p.device for p in serial.tools.list_ports.comports()]
selected_port = st.sidebar.selectbox("COM Port", ports, index=ports.index("COM3") if "COM3" in ports else 0)
selected_baud = st.sidebar.selectbox("Baud Rate", [9600, 115200, 921600], index=1)

col_run, col_stop = st.sidebar.columns(2)
if col_run.button("START", type="primary", use_container_width=True):
    st.session_state.running = True
if col_stop.button("STOP", use_container_width=True):
    st.session_state.running = False

if st.sidebar.button("Clear Graphs"):
    for key in st.session_state.data_buffer:
        st.session_state.data_buffer[key].extend([0.0] * 50)

# --- UI LAYOUT ---
st.title("Real-time Sensor Monitor")

# Placeholders that we will update
status = st.empty()
# Changed to 4 columns to fit the new Motor Condition metric
header_metrics = st.columns(4)
m_vib = header_metrics[0].empty()
m_sim = header_metrics[1].empty()
m_cur = header_metrics[2].empty()
m_cond = header_metrics[3].empty()

st.subheader("Vibration (3-Axis)")
vib_chart = st.empty()

col_left, col_right = st.columns(2)
with col_left:
    st.subheader("Similarity Score (%)")
    sim_chart = st.empty()
with col_right:
    st.subheader("Current Consumption (A)")
    cur_chart = st.empty()


# --- PARSER ---
def parse_line(line):
    try:
        # Format: 0.012,-0.004,1.003 | Similarity: 94% | Current: 1.236 A
        parts = line.split('|')
        v = parts[0].strip().split(',')
        vx, vy, vz = float(v[0]), float(v[1]), float(v[2])
        sim = float(re.search(r"Similarity:\s*(\d+)", parts[1]).group(1))
        curr = float(re.search(r"Current:\s*([\d.]+)", parts[2]).group(1))
        return vx, vy, vz, sim, curr
    except:
        return None


# --- MAIN LOOP ---
if st.session_state.running and selected_port:
    try:
        with serial.Serial(selected_port, selected_baud, timeout=0.05) as ser:
            status.success(f"Connected to {selected_port}")
            last_ui_update = time.time()

            while st.session_state.running:
                # 1. Read Serial Data
                line = ser.readline().decode('utf-8', errors='ignore').strip()

                if line:
                    data = parse_line(line)
                    if data:
                        vx, vy, vz, sim, curr = data
                        st.session_state.data_buffer['X'].append(vx)
                        st.session_state.data_buffer['Y'].append(vy)
                        st.session_state.data_buffer['Z'].append(vz)
                        st.session_state.data_buffer['Similarity'].append(sim)
                        st.session_state.data_buffer['Current'].append(curr)

                # 2. Throttle UI Updates (Crucial to prevent flashing)
                # Only update the browser every 100ms (10 times per second)
                if time.time() - last_ui_update > 0.1:

                    # --- MOTOR CONDITION LOGIC ---
                    # Grab the last 15 items from the similarity deque
                    recent_sims = list(st.session_state.data_buffer['Similarity'])[-15:]
                    avg_sim = sum(recent_sims) / len(recent_sims)

                    if avg_sim > 85:
                        cond_text = "🟢 Healthy"
                    elif 70 <= avg_sim <= 85:
                        cond_text = "🟡 Warning"
                    elif 40 <= avg_sim < 70:
                        cond_text = "🟠 Critical"
                    else:
                        cond_text = "🔴 Error"

                    # Update Metrics
                    m_vib.metric("Vibration Z", f"{vz} g")
                    m_sim.metric("Similarity", f"{sim}%")
                    m_cur.metric("Current", f"{curr} A")
                    m_cond.metric("Status (15-tick avg)", cond_text)  # Displays the new condition

                    # Update Vibration Chart
                    df_vib = pd.DataFrame({
                        'X-Axis': list(st.session_state.data_buffer['X']),
                        'Y-Axis': list(st.session_state.data_buffer['Y']),
                        'Z-Axis': list(st.session_state.data_buffer['Z'])
                    })
                    vib_chart.line_chart(df_vib, height=300, width='stretch')

                    # Update Similarity Chart
                    sim_chart.area_chart(list(st.session_state.data_buffer['Similarity']), height=250, width='stretch')

                    # Update Current Chart
                    cur_chart.line_chart(list(st.session_state.data_buffer['Current']), height=250, width='stretch')

                    last_ui_update = time.time()

    except Exception as e:
        status.error(f"Serial Error: {e}")
        st.session_state.running = False
else:
    status.info("Click START to begin data acquisition.")