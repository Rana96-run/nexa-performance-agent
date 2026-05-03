"""Google Ads — Channel Deep Dive"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
from channel_page import render_channel_page

st.set_page_config(page_title="Google Ads", page_icon="🔵", layout="wide")
st.title("🔵 Google Ads")
render_channel_page("google_ads", "Google Ads", has_keywords=True)
