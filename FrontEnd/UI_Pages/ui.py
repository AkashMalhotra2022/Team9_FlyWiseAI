import time
import streamlit as st
from clean_flywise.auth import verify_login, reset_password, register_user
from clean_flywise.chat import get_bot_response

# ---- Navigation helpers ----
def _rerun():
    """Handles Streamlit rerun for both old and new versions"""
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()

def go(view: str):
    """Navigate to a different page"""
    st.session_state.view = view
    _rerun()

def load_css(path: str = "clean_flywise/style.css") -> None:
    """Load CSS stylesheet"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning(f"CSS file not found: {path}")

# ------------------ Reusable Sidebar Component ------------------
def _sidebar(username: str):
    """Renders the sidebar greeting and menu buttons"""
    # Greeting
    st.markdown(f'<h3 style="color: #e8edf4; margin-bottom: 32px;">👋 Hi, {username or "traveler"}</h3>', unsafe_allow_html=True)

    # Menu buttons
    if st.button("🎯 Recommend Trips", use_container_width=True, key="menu_recommend"):
        go("home")

    if st.button("🔎 Search Flights", use_container_width=True, key="menu_search"):
        go("chat")

    if st.button("💬 Travel Chatbot", use_container_width=True, key="menu_chat"):
        go("chat")

    if st.button("🔒 Logout", use_container_width=True, key="menu_logout"):
        for k in ["logged_in", "username", "messages"]:
            st.session_state.pop(k, None)
        go("landing")

# ------------------ Pages ------------------
def page_login():
    """Login page"""
    st.markdown('<div class="card" style="max-width:520px;margin:60px auto;">', unsafe_allow_html=True)
    st.markdown("### Sign in to FlyWise")
    
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="you@example.com", key="login_username")
        password = st.text_input("Password", type="password", placeholder="••••••••", key="login_password")
        submitted = st.form_submit_button("Sign In", use_container_width=True)
        
        if submitted:
            if username and password and verify_login(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("✅ Login successful!")
                time.sleep(0.2)
                go("home")
            else:
                st.error("❌ Invalid credentials")
    
    c1, c2 = st.columns(2)
    with c1:
        st.button("Create Account", use_container_width=True, 
                  on_click=lambda: st.session_state.update(view="register"), key="nav_to_register")
    with c2:
        st.button("Reset Password", use_container_width=True, 
                  on_click=lambda: st.session_state.update(view="reset"), key="nav_to_reset")
    
    st.markdown("</div>", unsafe_allow_html=True)


def page_reset():
    """Password reset page"""
    st.markdown('<div class="card" style="max-width:560px;margin:40px auto;">', unsafe_allow_html=True)
    st.markdown("### Reset Password")
    
    with st.form("reset_form"):
        user = st.text_input("Username", key="reset_username")
        email = st.text_input("Registered Email", key="reset_email")
        new_pass = st.text_input("New Password", type="password", key="reset_new_pass")
        confirm = st.text_input("Confirm Password", type="password", key="reset_confirm_pass")
        submitted = st.form_submit_button("Update Password", use_container_width=True)
        
        if submitted:
            if not user or not email or not new_pass:
                st.error("Please fill all fields.")
            elif new_pass != confirm:
                st.error("Passwords do not match.")
            elif reset_password(user, email, new_pass):
                st.success("✅ Password updated. Redirecting to Sign In…")
                time.sleep(0.6)
                go("login")
            else:
                st.error("❌ Invalid username or email.")
    
    st.button("⬅️ Back", use_container_width=True, 
              on_click=lambda: st.session_state.update(view="login"), key="reset_back")
    st.markdown("</div>", unsafe_allow_html=True)


def page_register():
    """Registration page"""
    st.markdown('<div class="card" style="max-width:560px;margin:40px auto;">', unsafe_allow_html=True)
    st.markdown("### Create Account")
    
    with st.form("register_form"):
        username = st.text_input("Username", key="register_username")
        email = st.text_input("Email", key="register_email")
        password = st.text_input("Password", type="password", key="register_password")
        confirm = st.text_input("Confirm Password", type="password", key="register_confirm")
        agree = st.checkbox("I agree to the Terms & Privacy", key="register_agree")
        submitted = st.form_submit_button("Create Account", use_container_width=True)
        
        if submitted:
            if not agree:
                st.warning("Please accept the Terms & Privacy to continue.")
            elif password != confirm:
                st.error("Passwords do not match.")
            else:
                ok, msg = register_user(username, email, password)
                if ok:
                    st.success("✅ " + msg + " Redirecting to Sign In…")
                    time.sleep(0.6)
                    go("login")
                else:
                    st.error("❌ " + msg)
    
    st.button("⬅️ Back", use_container_width=True, 
              on_click=lambda: st.session_state.update(view="login"), key="register_back")
    st.markdown("</div>", unsafe_allow_html=True)


def page_home():
    """Home page with dark sidebar and main content"""
    username = st.session_state.get("username", "traveler")
    
    # Use Streamlit columns
    col1, col2 = st.columns([0.20, 0.80], gap="large")
    
    with col1:
        # Apply inline styles with gradient sidebar
        st.markdown('''
            <style>
            /* Gradient sidebar - Navy blue fading effect */
            div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="column"]:first-child,
            div[data-testid="column"]:nth-child(1),
            [data-testid="stHorizontalBlock"] > div:nth-child(1) {
                background: linear-gradient(180deg, #334155 0%, #1e293b 50%, #0f172a 100%) !important;
                padding: 32px 24px !important;
                min-height: 100vh !important;
                border-right: 1px solid rgba(255, 255, 255, 0.1) !important;
                box-shadow: 4px 0 20px rgba(0, 0, 0, 0.5) !important;
            }
            
            /* Sidebar text color */
            div[data-testid="column"]:nth-child(1) * {
                color: #e2e8f0 !important;
            }
            
            /* Sidebar buttons with subtle gradient */
            [data-testid="stHorizontalBlock"] > div:nth-child(1) .stButton > button {
                background: linear-gradient(135deg, rgba(71, 85, 105, 0.4), rgba(51, 65, 85, 0.6)) !important;
                border: 1px solid rgba(148, 163, 184, 0.3) !important;
                color: #e2e8f0 !important;
                border-radius: 10px !important;
                padding: 12px 16px !important;
                width: 100% !important;
                font-size: 15px !important;
                font-weight: 600 !important;
                margin-bottom: 12px !important;
                text-align: left !important;
                transition: all 0.3s ease !important;
                backdrop-filter: blur(10px) !important;
            }
            
            [data-testid="stHorizontalBlock"] > div:nth-child(1) .stButton > button:hover {
                background: linear-gradient(135deg, rgba(100, 116, 139, 0.6), rgba(71, 85, 105, 0.8)) !important;
                border: 1px solid rgba(148, 163, 184, 0.5) !important;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
                transform: translateX(4px) !important;
            }
            
            /* Main content area - complementary dark */
            [data-testid="stHorizontalBlock"] > div:nth-child(2) {
                background-color: #0a0e14 !important;
                padding: 32px 48px !important;
                min-height: 100vh !important;
            }
            </style>
        ''', unsafe_allow_html=True)
        
        # Greeting
        st.markdown(f'<h3 style="color: #f1f5f9; margin-bottom: 32px; font-size: 24px; font-weight: 700;">👋 Hi, {username or "traveler"}</h3>', unsafe_allow_html=True)
        
        # Menu buttons
        if st.button("🎯 Recommend Trips", use_container_width=True, key="menu_recommend"):
            go("home")
        
        if st.button("🔎 Search Flights", use_container_width=True, key="menu_search"):
            go("chat")
        
        if st.button("💬 Travel Chatbot", use_container_width=True, key="menu_chat"):
            go("chat")
        
        if st.button("🔒 Logout", use_container_width=True, key="menu_logout"):
            for k in ["logged_in", "username", "messages"]:
                st.session_state.pop(k, None)
            go("landing")
    
    with col2:
        st.markdown(
            '''
            <div style="text-align: center; padding-top: 100px;">
                <h1 style="font-size: 3.5em; margin-bottom: 20px;">
                    ✈️ Welcome to <span style="color: #22c55e;">FlyWise</span>
                </h1>
                <p style="font-size: 1.3em; color: #e8edf4; margin-bottom: 16px;">
                    Discover travel recommendations personalized just for you!
                </p>
                <p style="font-size: 1.1em; color: #a9b1bd; max-width: 900px; margin: 0 auto;">
                    Our system uses your preferences and previous activity to surface the best flight and stay options.
                </p>
            </div>
            ''',
            unsafe_allow_html=True
        )
        
        st.markdown('<div style="margin-top:48px; text-align: center;">', unsafe_allow_html=True)
        if st.button("✨ Generate Recommendations", key="cta_generate", use_container_width=False):
            go("chat")
        st.markdown('</div>', unsafe_allow_html=True)


def page_chat():
    """Chat page with dark sidebar and chat interface"""
    username = st.session_state.get("username", "traveler")
    
    # Use Streamlit columns
    col1, col2 = st.columns([0.20, 0.80], gap="large")
    
    with col1:
        # Apply inline styles directly
        st.markdown('''
            <style>
            /* Gradient sidebar - Navy blue fading effect */
            div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="column"]:first-child,
            div[data-testid="column"]:nth-child(1),
            [data-testid="stHorizontalBlock"] > div:nth-child(1) {
                background: linear-gradient(180deg, #334155 0%, #1e293b 50%, #0f172a 100%) !important;
                padding: 32px 24px !important;
                min-height: 100vh !important;
                border-right: 1px solid rgba(255, 255, 255, 0.1) !important;
                box-shadow: 4px 0 20px rgba(0, 0, 0, 0.5) !important;
            }
            
            /* Sidebar text color */
            div[data-testid="column"]:nth-child(1) * {
                color: #e2e8f0 !important;
            }
            
            /* Sidebar buttons with subtle gradient */
            [data-testid="stHorizontalBlock"] > div:nth-child(1) .stButton > button {
                background: linear-gradient(135deg, rgba(71, 85, 105, 0.4), rgba(51, 65, 85, 0.6)) !important;
                border: 1px solid rgba(148, 163, 184, 0.3) !important;
                color: #e2e8f0 !important;
                border-radius: 10px !important;
                padding: 12px 16px !important;
                width: 100% !important;
                font-size: 15px !important;
                font-weight: 600 !important;
                margin-bottom: 12px !important;
                text-align: left !important;
                transition: all 0.3s ease !important;
                backdrop-filter: blur(10px) !important;
            }
            
            [data-testid="stHorizontalBlock"] > div:nth-child(1) .stButton > button:hover {
                background: linear-gradient(135deg, rgba(100, 116, 139, 0.6), rgba(71, 85, 105, 0.8)) !important;
                border: 1px solid rgba(148, 163, 184, 0.5) !important;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
                transform: translateX(4px) !important;
            }
            
            /* Main content area - complementary dark */
            [data-testid="stHorizontalBlock"] > div:nth-child(2) {
                background-color: #0a0e14 !important;
                padding: 32px 48px !important;
                min-height: 100vh !important;
            }
            </style>
        ''', unsafe_allow_html=True)
        
        # Greeting
        st.markdown(f'<h3 style="color: #1f2937; margin-bottom: 32px; font-size: 24px; font-weight: 700;">👋 Hi, {username or "traveler"}</h3>', unsafe_allow_html=True)
        
        # Menu buttons
        if st.button("🎯 Recommend Trips", use_container_width=True, key="menu_recommend_chat"):
            go("home")
        
        if st.button("🔎 Search Flights", use_container_width=True, key="menu_search_chat"):
            go("chat")
        
        if st.button("💬 Travel Chatbot", use_container_width=True, key="menu_chat_chat"):
            go("chat")
        
        if st.button("🔒 Logout", use_container_width=True, key="menu_logout_chat"):
            for k in ["logged_in", "username", "messages"]:
                st.session_state.pop(k, None)
            go("landing")
    
    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 💬 Travel Assistant")
        
        # Display chat messages
        for m in st.session_state.messages:
            cls = "user-bubble" if m["role"] == "user" else "bot-bubble"
            st.markdown(f'<div class="{cls}">{m["content"]}</div>', unsafe_allow_html=True)
        
        # Chat input form
        with st.form("chat_form", clear_on_submit=True):
            user_msg = st.text_input("Message", placeholder="Ask me about flights, baggage, refunds…", key="chat_input")
            submitted = st.form_submit_button("Send", use_container_width=False)
            
            if submitted and user_msg:
                st.session_state.messages.append({"role": "user", "content": user_msg})
                bot_reply = get_bot_response(user_msg)
                st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                _rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)