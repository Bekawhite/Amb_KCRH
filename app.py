# KCRH_App.py (Corrected First Half)
# Kisumu County Referral Hospital - Streamlit App
# Combines referral system, ambulance tracking, communications, handover forms,
# mapping, analytics and offline sync (demo / simulation version).

import streamlit as st
import pandas as pd
import numpy as np
import datetime
import random
from typing import List, Dict
import time
import io

# Mapping & geolocation
import folium
from geopy.distance import geodesic
import streamlit.components.v1 as components

# Visualization
import matplotlib.pyplot as plt

# Faker for simulated content
from faker import Faker
faker = Faker()

# PDF generation
from fpdf import FPDF

# -----------------------------
# Core data classes
# -----------------------------
class Hospital:
    def __init__(self, name, location, capacity, hospital_type="general"):
        self.name = name
        self.location = location  # (lat, lon)
        self.capacity = capacity
        self.available_beds = capacity
        self.type = hospital_type
        self.referrals_received = []

    def admit_patient(self, patient):
        if self.available_beds > 0:
            self.available_beds -= 1
            self.referrals_received.append(patient)
            patient.status = "admitted"
            return True
        return False

    def discharge_patient(self, patient):
        if patient in self.referrals_received:
            self.referrals_received.remove(patient)
            self.available_beds += 1
            patient.status = "discharged"
            return True
        return False


class Patient:
    def __init__(self, name, condition, severity, vital_signs=None):
        self.name = name
        self.condition = condition
        self.severity = severity
        self.vital_signs = vital_signs or {}
        self.status = "waiting"
        self.transfer_completion_time = None


class Ambulance:
    def __init__(self, amb_id, location):
        self.id = amb_id
        self.location = location
        self.status = "available"  # available, dispatched, en_route, arrived
        self.current_patient = None
        self.destination = None
        self.route = []
        self.eta = None

    def dispatch(self, patient, destination):
        self.status = "dispatched"
        self.current_patient = patient
        self.destination = destination

    def complete_transfer(self):
        self.status = "available"
        if self.current_patient:
            self.current_patient.transfer_completion_time = datetime.datetime.now()
        self.current_patient = None
        self.destination = None


# -----------------------------
# Specialized systems
# -----------------------------
class ReferralSystem:
    def __init__(self):
        self.hospitals: List[Hospital] = []
        self.ambulances: List[Ambulance] = []
        self.referral_requests: List[Dict] = []
        self.referral_history = pd.DataFrame(columns=[
            "Patient", "From Hospital", "To Hospital", "Ambulance",
            "Status", "Request Time", "Completion Time"
        ])

    def add_hospital(self, hospital: Hospital):
        self.hospitals.append(hospital)

    def add_ambulance(self, ambulance: Ambulance):
        self.ambulances.append(ambulance)

    def find_available_ambulance(self):
        return next((amb for amb in self.ambulances if amb.status == "available"), None)

    def create_referral(self, patient: Patient, from_hospital: Hospital, to_hospital: Hospital, ambulance: Ambulance=None):
        amb = ambulance or self.find_available_ambulance()
        if not amb:
            return None

        referral = {
            "id": len(self.referral_requests) + 1,
            "patient": patient,
            "from_hospital": from_hospital,
            "to_hospital": to_hospital,
            "ambulance": amb,
            "timestamp": datetime.datetime.now(),
            "status": "in_transit"
        }

        amb.dispatch(patient, to_hospital)
        self.referral_requests.append(referral)
        return referral

    def complete_referral(self, referral_id: int):
        referral = next((r for r in self.referral_requests if r["id"] == referral_id), None)
        if not referral:
            return None

        referral["ambulance"].complete_transfer()
        referral["status"] = "completed"
        completion_time = datetime.datetime.now()

        new_entry = {
            "Patient": referral["patient"].name,
            "From Hospital": referral["from_hospital"].name,
            "To Hospital": referral["to_hospital"].name,
            "Ambulance": referral["ambulance"].id,
            "Status": referral["status"],
            "Request Time": referral["timestamp"],
            "Completion Time": completion_time
        }
        self.referral_history = pd.concat([self.referral_history, pd.DataFrame([new_entry])], ignore_index=True)
        return referral


class AmbulanceTracker:
    def __init__(self, system: ReferralSystem):
        self.system = system

    def calculate_distance(self, loc1, loc2):
        return geodesic(loc1, loc2).km

    def simulate_movement(self, ambulance: Ambulance, dest_loc, speed_kmh=60):
        distance_km = self.calculate_distance(ambulance.location, dest_loc)
        minutes = (distance_km / speed_kmh) * 60
        ambulance.eta = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
        ambulance.route = self.generate_route(ambulance.location, dest_loc)
        ambulance.status = "en_route"
        return {"distance_km": distance_km, "eta": ambulance.eta}

    def generate_route(self, start, end, num_points=6):
        lat_diff = (end[0] - start[0]) / (num_points + 1)
        lon_diff = (end[1] - start[1]) / (num_points + 1)
        pts = []
        for i in range(1, num_points + 1):
            pts.append((start[0] + lat_diff * i + random.uniform(-0.0005, 0.0005),
                        start[1] + lon_diff * i + random.uniform(-0.0005, 0.0005)))
        return pts


class CommunicationSystem:
    def __init__(self):
        self.messages = []

    def send_message(self, sender, recipient, message_type, content, urgent=False):
        msg = {
            "id": len(self.messages) + 1,
            "sender": sender,
            "recipient": recipient,
            "type": message_type,
            "content": content,
            "urgent": urgent,
            "timestamp": datetime.datetime.now(),
            "read": False
        }
        self.messages.append(msg)
        return msg

    def get_messages_for(self, recipient):
        return [m for m in self.messages if m["recipient"] == recipient]


# -----------------------------
# Session State Initialization
# -----------------------------
if 'ref_sys' not in st.session_state:
    st.session_state.ref_sys = ReferralSystem()
ref_sys = st.session_state.ref_sys

if 'comm_system' not in st.session_state:
    st.session_state.comm_system = CommunicationSystem()
comm_system = st.session_state.comm_system

if 'patients' not in st.session_state:
    st.session_state.patients = [
        Patient("John Otieno", "trauma", 4, {"bp": "110/70", "hr": 110}),
        Patient("Mary Achieng'", "maternity", 3, {"bp": "120/80", "hr": 90}),
        Patient("Beatrice Ayako", "cardiac", 5, {"bp": "90/60", "hr": 140})
    ]
patients = st.session_state.patients

# -----------------------------
# Helper function
# -----------------------------
def referrals_to_df(system: ReferralSystem):
    if system.referral_history.empty:
        return pd.DataFrame(columns=["Patient", "From Hospital", "To Hospital", "Ambulance", "Status", "Request Time", "Completion Time"])
    return system.referral_history.copy()

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Kisumu County Referral System", layout="wide")
st.title("🏥 Kisumu County Referral Hospital System")

menu = ["Dashboard", "Create Referral", "Ambulance Tracking", "Communications", "Handover Forms", "Offline Queue"]
choice = st.sidebar.selectbox("Navigation", menu)

# -----------------------------
# Dashboard
# -----------------------------
if choice == "Dashboard":
    st.subheader("Hospital Overview")
    for hosp in ref_sys.hospitals:
        st.write(f"**{hosp.name}** ({hosp.type}) - Beds: {hosp.available_beds}/{hosp.capacity}")
        st.write(f"Referrals received: {len(hosp.referrals_received)}")

    st.subheader("Referral History")
    df_ref = referrals_to_df(ref_sys)
    st.dataframe(df_ref)

# -----------------------------
# Create Referral
# -----------------------------
elif choice == "Create Referral":
    st.subheader("Create a New Referral")

    patient_names = [p.name for p in patients if p.status != "admitted"]
    if not patient_names:
        st.warning("No patients available for referral.")
    else:
        selected_patient_name = st.selectbox("Select Patient", patient_names)
        patient_obj = next((p for p in patients if p.name == selected_patient_name), None)

        from_hospital_name = st.selectbox("From Hospital", [h.name for h in ref_sys.hospitals])
        to_hospital_name = st.selectbox("To Hospital", [h.name for h in ref_sys.hospitals if h.name != from_hospital_name])

        if st.button("Create Referral"):
            from_hosp_obj = next(h for h in ref_sys.hospitals if h.name == from_hospital_name)
            to_hosp_obj = next(h for h in ref_sys.hospitals if h.name == to_hospital_name)

            referral = ref_sys.create_referral(patient_obj, from_hosp_obj, to_hosp_obj)
            if referral:
                st.success(f"Referral created! Ambulance {referral['ambulance'].id} dispatched.")
            else:
                st.error("No available ambulance. Please try again later.")

# -----------------------------
# Ambulance Tracking
# -----------------------------
elif choice == "Ambulance Tracking":
    st.subheader("Ambulance Status")
    for amb in ref_sys.ambulances:
        st.write(f"**{amb.id}** - Status: {amb.status}")
        if amb.status != "available" and amb.current_patient:
            st.write(f"Patient: {amb.current_patient.name} → Destination: {amb.destination.name}")
            st.write(f"ETA: {amb.eta if amb.eta else 'Calculating...'}")

    st.subheader("Map View")
    map_center = ref_sys.hospitals[0].location
    m = folium.Map(location=map_center, zoom_start=12)

    # Plot hospitals
    for hosp in ref_sys.hospitals:
        folium.Marker(
            location=hosp.location,
            popup=f"{hosp.name}\nBeds: {hosp.available_beds}/{hosp.capacity}",
            icon=folium.Icon(color="green", icon="plus-sign")
        ).add_to(m)

    # Plot ambulances
    for amb in ref_sys.ambulances:
        color = "blue" if amb.status == "available" else "red"
        folium.Marker(
            location=amb.location,
            popup=f"{amb.id}\nStatus: {amb.status}",
            icon=folium.Icon(color=color, icon="ambulance")
        ).add_to(m)

        if amb.route:
            folium.PolyLine(locations=[amb.location] + amb.route + ([amb.destination.location] if amb.destination else []),
                            color="orange", weight=3, opacity=0.7).add_to(m)

    components.html(m._repr_html_(), height=500)

# -----------------------------
# Communications
# -----------------------------
elif choice == "Communications":
    st.subheader("Send Message")

    sender = st.text_input("Sender")
    recipient = st.text_input("Recipient")
    msg_type = st.selectbox("Message Type", ["general", "urgent", "alert"])
    content = st.text_area("Message Content")
    urgent = st.checkbox("Mark as urgent")

    if st.button("Send Message"):
        msg = comm_system.send_message(sender, recipient, msg_type, content, urgent)
        st.success(f"Message sent! ID: {msg['id']}")

    st.subheader("Inbox")
    recipient_inbox = st.text_input("View Inbox for Recipient")
    if recipient_inbox:
        msgs = comm_system.get_messages_for(recipient_inbox)
        for m in msgs:
            st.write(f"From: {m['sender']} | Type: {m['type']} | Urgent: {m['urgent']}")
            st.write(f"Content: {m['content']}")
            st.write(f"Timestamp: {m['timestamp']}")
            st.write("---")

# -----------------------------
# Handover Forms
# -----------------------------
elif choice == "Handover Forms":
    st.subheader("Digital Handover Forms")

    handover_system = DigitalHandoverSystem()
    if st.button("Generate Handover PDFs for Completed Referrals"):
        for idx, row in referrals_to_df(ref_sys).iterrows():
            patient_name = row["Patient"]
            patient_obj = next((p for p in patients if p.name == patient_name), None)
            if not patient_obj:
                continue

            referral_dict = {
                "patient": patient_obj,
                "from_hospital": next(h for h in ref_sys.hospitals if h.name == row["From Hospital"]),
                "to_hospital": next(h for h in ref_sys.hospitals if h.name == row["To Hospital"])
            }

            form = handover_system.create_handover(referral_dict)

            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, f"Handover Form: {form['form_id']}", ln=True)
            pdf.cell(0, 10, f"Patient: {form['patient']}", ln=True)
            pdf.cell(0, 10, f"Condition: {form['condition']}", ln=True)
            pdf.cell(0, 10, f"From: {form['sending']}", ln=True)
            pdf.cell(0, 10, f"To: {form['receiving']}", ln=True)
            pdf.cell(0, 10, f"Vitals: {form['vitals']}", ln=True)
            pdf_output = io.BytesIO()
            pdf.output(pdf_output)
            st.download_button(f"Download {form['form_id']}", data=pdf_output.getvalue(),
                               file_name=f"{form['form_id']}.pdf")

# -----------------------------
# Offline Queue
# -----------------------------
elif choice == "Offline Queue":
    st.subheader("Offline Queue Management")
    offline_mgr = OfflineManager()

    if st.button("Go Offline"):
        offline_mgr.go_offline()
        st.info("App is now offline.")

    if st.button("Go Online & Sync"):
        offline_mgr.go_online()
        success = offline_mgr.sync()
        if success:
            st.success("Offline queue synced successfully!")
        else:
            st.warning("Still offline. Cannot sync.")

    st.write("Offline Queue:")
    st.dataframe(pd.DataFrame(offline_mgr.offline_queue))
