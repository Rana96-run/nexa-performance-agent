"""Meta Ads — Channel Deep Dive"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
from channel_page import render_channel_page

st.set_page_config(page_title="Meta Ads", page_icon="🟦", layout="wide")
st.title("🟦 Meta Ads")
render_channel_page("meta", "Meta Ads", has_keywords=False)
