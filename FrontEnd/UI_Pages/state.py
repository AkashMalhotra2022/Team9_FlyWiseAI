import streamlit as st

def init_state():
    """Initialize all session state variables"""
    
    # Authentication state
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if 'username' not in st.session_state:
        st.session_state.username = None
    
    # Navigation state
    if 'view' not in st.session_state:
        st.session_state.view = 'landing'
    
    # Chat messages
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    # User preferences (can be expanded)
    if 'user_preferences' not in st.session_state:
        st.session_state.user_preferences = {
            'preferred_airlines': [],
            'budget_range': None,
            'travel_class': 'Economy'
        }