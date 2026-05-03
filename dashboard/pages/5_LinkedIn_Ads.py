"""LinkedIn Ads — Channel Deep Dive"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
from channel_page import render_channel_page

st.set_page_config(page_title="LinkedIn Ads", page_icon="🔷", layout="wide")
st.title("🔷 LinkedIn Ads")
render_channel_page("linkedin", "LinkedIn Ads", has_keywords=False)
