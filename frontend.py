import streamlit as st
import requests
import base64
import urllib.parse
import re

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="SnapNest-Tridibesh",
    layout="wide",
    initial_sidebar_state="expanded"
)


# css
st.markdown("""
<style>
.post-card {
    background: #ffffff;
    padding: 1.2rem;
    border-radius: 14px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    margin-bottom: 1.5rem;
}
.username {
    font-weight: 600;
}
.date {
    font-size: 12px;
    color: #888;
}
.caption {
    margin: 8px 0;
    font-size: 15px;
}
.comment {
    font-size: 14px;
    margin-bottom: 4px;
}
</style>
""", unsafe_allow_html=True)


# session state
if "token" not in st.session_state:
    st.session_state.token = None
if "user" not in st.session_state:
    st.session_state.user = None


# helper functions
def get_headers():
    if st.session_state.token:
        return {"Authorization": f"Bearer {st.session_state.token}"}
    return {}

def encode_text_for_overlay(text):
    if not text:
        return ""
    b64 = base64.b64encode(text.encode()).decode()
    return urllib.parse.quote(b64)

def create_transformed_url(url, caption=None):
    if not caption:
        return url
    encoded = encode_text_for_overlay(caption)
    overlay = f"l-text,ie-{encoded},ly-N20,lx-20,fs-60,co-white,bg-000000A0,l-end"
    parts = url.split("/")
    return f"{parts[0]}//{parts[2]}/{parts[3]}/tr:{overlay}/{'/'.join(parts[4:])}"

def is_valid_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


# login / register
def login_page():
    st.markdown("""
    <h1 style='text-align:center;'>SnapNest</h1>        
    <p style='text-align:center;'>Login / Signup in our FastAPI Social Platform</p>
    """, unsafe_allow_html=True)

    username = st.text_input("Username *", placeholder="Enter your name")
    email = st.text_input("Email *", placeholder="Enter your email ID")
    password = st.text_input(
        "Password *",
        type="password",
        placeholder="Enter your password"
    )

    # ---------------- LOGIN ----------------
    if st.button("Login", type="primary", use_container_width=True):
        if not email or not password:
            st.warning("Email and password are required")
            return

        if not is_valid_email(email):
            st.error("Please enter a valid email address")
            return

        with st.spinner("Logging in..."):
            try:
                res = requests.post(
                    f"{API_BASE}/auth/jwt/login",
                    data={"username": email, "password": password},
                    timeout=5
                )

                if res.status_code == 200:
                    st.session_state.token = res.json()["access_token"]

                    user_res = requests.get(
                        f"{API_BASE}/users/me",
                        headers=get_headers(),
                        timeout=5
                    )
                    st.session_state.user = user_res.json()
                    st.rerun()
                else:
                    st.error("Invalid email or password")

            except requests.exceptions.Timeout:
                st.error("Server timeout. Please try again.")
            except requests.exceptions.RequestException:
                st.error("Server not reachable")

    # ---------------- SIGNUP ----------------
    if st.button("Create Account", use_container_width=True):
        if not username or not email or not password:
            st.warning("All fields are required")
            return

        if not is_valid_email(email):
            st.error("Please enter a valid email address")
            return

        with st.spinner("Creating account..."):
            try:
                res = requests.post(
                    f"{API_BASE}/auth/register",
                    json={
                        "email": email,
                        "password": password,
                        "username": username
                    },
                    timeout=5
                )

                if res.status_code == 201:
                    st.success("Account created! Please login.")
                else:
                    detail = res.json().get("detail", "Registration failed")
                    st.error(detail)

            except requests.exceptions.Timeout:
                st.error("Server timeout. Please try again.")
            except requests.exceptions.RequestException:
                st.error("Server not reachable")

# upload
def upload_page():
    st.title("📸 Create Post")

    file = st.file_uploader(
        "Upload image or video",
        type=["png", "jpg", "jpeg", "mp4", "mov", "webm"]
    )
    caption = st.text_area("Caption")

    if st.button("Publish", type="primary", use_container_width=True):
        if not file:
            st.warning("Please select a file")
            return

        files = {"file": (file.name, file.getvalue(), file.type)}
        data = {"caption": caption}

        res = requests.post(
            f"{API_BASE}/upload",
            files=files,
            data=data,
            headers=get_headers(),
            timeout=10
        )

        if res.status_code == 200:
            st.success("Post uploaded!")
            st.rerun()
        else:
            st.error("Upload failed")

# home
def home_page():
    st.title("🏠 SnapNest")

    res = requests.get(
        f"{API_BASE}/home",
        headers=get_headers(),
        timeout=5
    )

    posts = res.json()["posts"]

    for post in posts:
        with st.container():
            st.markdown('<div class="post-card">', unsafe_allow_html=True)

            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(
                    f"<div class='username'>👤 {post['username']}</div>"
                    f"<div class='date'>{post['created_at'][:10]}</div>",
                    unsafe_allow_html=True
                )

            with col2:
                if post["is_owner"]:
                    if st.button("🗑️", key=f"del_{post['id']}"):
                        requests.delete(
                            f"{API_BASE}/posts/{post['id']}",
                            headers=get_headers(),
                            timeout=5
                        )
                        st.rerun()

            # caption
            if post["caption"]:
                st.markdown(f"<div class='caption'>{post['caption']}</div>", unsafe_allow_html=True)

            # media
            if post["file_type"] == "image":
                st.image(post["url"], use_container_width=True)
            else:
                st.video(post["url"])

            # like section
            col1, col2 = st.columns([1, 5])
            with col1:
                icon = "❤️" if post["liked"] else "🤍"
                if st.button(icon, key=f"like_{post['id']}"):
                    requests.post(
                        f"{API_BASE}/posts/{post['id']}/like",
                        headers=get_headers(),
                        timeout=5
                    )
                    st.rerun()

            with col2:
                st.write(f"{post['likes']} likes")

            # comments
            st.markdown("**Comments**")
            for c in post["comments"]:
                st.markdown(
                    f"<div class='comment'><b>{c['username']}</b>: {c['text']}</div>",
                    unsafe_allow_html=True
                )

            comment = st.text_input(
                "Add a comment...",
                key=f"comment_{post['id']}"
            )

            if st.button("Post", key=f"post_{post['id']}"):
                requests.post(
                    f"{API_BASE}/posts/{post['id']}/comment",
                    data={"text": comment},
                    headers=get_headers(),
                    timeout=5
                )
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

# main
if st.session_state.user is None:
    login_page()
else:
    st.sidebar.markdown(
        f"### 👤 Profile\n**{st.session_state.user['username']}**"
    )

    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    page = st.sidebar.radio("Navigate", ["🏠 Home", "📸 Upload"])

    if page == "🏠 Home":
        home_page()
    else:
        upload_page()
