from dotenv import load_dotenv
import streamlit as st
from clean_flywise.ui import (
    load_css,
    page_login,
    page_register,
    page_reset,
    page_home,
    page_chat
)
from clean_flywise.state import init_state

load_dotenv()

# Page Setup
st.set_page_config(
    page_title='FlyWise - Smart Travel Assistant',
    page_icon='✈️',
    layout='wide',
    initial_sidebar_state='collapsed'
)

# Load CSS
load_css("clean_flywise/style.css")

# Initialize Session State
init_state()

# Landing Page
def landing_page():
    st.markdown(
        """
        <div style='text-align: center; padding-top: 50px;'>
            <h1 style='font-size: 3.5em; margin-bottom: 10px;'>✈️ Welcome to <span style="color:#22c55e;">FlyWise</span></h1>
            <p style='font-size: 1.3em; margin-top: 10px; color: #a9b1bd;'>
                Your intelligent travel companion for discovering personalized flight recommendations and travel insights.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    st.markdown(
        """
        <div style='text-align: center; margin-top: 20px;'>
            <p style='font-size: 1.15em; color: #a9b1bd;'>🌍 Access <strong>10,000+</strong> flight routes worldwide — budget airlines, premium carriers, direct flights, and more.</p>
            <p style='font-size: 1.08em; color: #9ca3af;'>FlyWise helps you find the perfect flights that match <em>your preferences</em> and <em>budget</em>.</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    st.markdown("<div style='margin: 40px 0;'><hr style='border-color: #2b3340;'></div>", unsafe_allow_html=True)
    
    # Features Section
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(
            """
            <div class="card" style="text-align: center; padding: 30px 20px;">
                <h2 style="font-size: 2.5em; margin: 0;">🎯</h2>
                <h3 style="margin: 15px 0 10px 0;">Smart Recommendations</h3>
                <p style="color: #a9b1bd;">Get personalized flight suggestions based on your travel history and preferences</p>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    with col2:
        st.markdown(
            """
            <div class="card" style="text-align: center; padding: 30px 20px;">
                <h2 style="font-size: 2.5em; margin: 0;">🔍</h2>
                <h3 style="margin: 15px 0 10px 0;">Advanced Search</h3>
                <p style="color: #a9b1bd;">Find the best flights with our powerful search filters and real-time pricing</p>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    with col3:
        st.markdown(
            """
            <div class="card" style="text-align: center; padding: 30px 20px;">
                <h2 style="font-size: 2.5em; margin: 0;">💬</h2>
                <h3 style="margin: 15px 0 10px 0;">AI Travel Assistant</h3>
                <p style="color: #a9b1bd;">Chat with our intelligent bot for instant answers about flights and travel</p>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    st.markdown("<div style='margin: 40px 0;'></div>", unsafe_allow_html=True)
    
    # CTA Buttons
    st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        pass
    
    with col2:
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🔐 Login", use_container_width=True, key="landing_login"):
                st.session_state.view = 'login'
                st.rerun()
        with col_b:
            if st.button("📝 Register", use_container_width=True, key="landing_register"):
                st.session_state.view = 'register'
                st.rerun()
    
    with col3:
        pass
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Footer
    st.markdown(
        """
        <div style='text-align: center; margin-top: 80px; padding: 20px; color: #6b7280;'>
            <p style='font-size: 0.9em;'>✨ Powered by advanced AI and real-time flight data</p>
        </div>
        """,
        unsafe_allow_html=True
    )


# Main Page Routing
def main():
    view = st.session_state.get("view", "landing")
    
    # If not logged in, only allow landing, login, register, reset
    if not st.session_state.get("logged_in", False):
        if view not in ("landing", "login", "register", "reset"):
            view = "landing"
    
    # Route to appropriate page
    if view == "landing":
        landing_page()
    elif view == "login":
        page_login()
    elif view == "register":
        page_register()
    elif view == "reset":
        page_reset()
    elif view == "home":
        page_home()
    elif view == "chat":
        page_chat()
    else:
        landing_page()


# Run the app
if __name__ == "__main__":
    main()