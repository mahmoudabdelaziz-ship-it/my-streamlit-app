import streamlit as st
import time

# Set up the page title and description
st.set_page_config(page_title="Interactive Test App", page_icon="⚙️")
st.title("Waiting for User Response Test")
st.write("This app will freeze at checkpoints and wait for your input before moving to the next block of code.")

st.markdown("---")

# 🧠 Initialize Session State variables to track progress
if "step_1_done" not in st.session_state:
    st.session_state.step_1_done = False
if "step_2_done" not in st.session_state:
    st.session_state.step_2_done = False
if "chosen_action" not in st.session_state:
    st.session_state.chosen_action = None

# ==========================================
# 📥 STEP 1: Provide the Input Data
# ==========================================
st.subheader("Step 1: Provide the Input Data")
user_text = st.text_area("Type a paragraph or sentence here for the server to process:", 
                         placeholder="The quick brown fox jumps over the lazy dog...")

# Button to lock in Step 1 and reveal Step 2
if user_text and not st.session_state.step_1_done:
    if st.button("Confirm Text & Proceed to Step 2 ➡️"):
        st.session_state.step_1_done = True
        st.rerun()

# Reset state if the user completely clears the text box
if not user_text:
    st.session_state.step_1_done = False
    st.session_state.step_2_done = False

# ==========================================
# 📥 STEP 2: Choose an Action (Only shows if Step 1 is done)
# ==========================================
if st.session_state.step_1_done:
    st.success("✨ Step 1 Passed! The server received your text.")
    st.markdown("---")
    st.subheader("Step 2: Choose an Action")
    st.write("Pick an option and press **Enter** (or click the button) to execute.")
    
    # Using a form so Enter key works perfectly
    with st.form(key="action_form"):
        action = st.selectbox("What should the server do with your text?", 
                              ["Count Words", "Convert to UPPERCASE", "Simulate AI Summary"])
        
        submit_button = st.form_submit_button(label="🚀 Execute Selected Action")
        
    if submit_button:
        # Save the choices to session state so they don't disappear
        st.session_state.chosen_action = action
        st.session_state.step_2_done = True
        
        # Show a loading spinner to simulate processing time
        with st.spinner("Server is processing... please wait."):
            time.sleep(2) 
            
        st.balloons() # Fun celebration!

# ==========================================
# 📥 STEP 3: Output Results (Only shows after Step 2 executes)
# ==========================================
if st.session_state.step_2_done:
    st.markdown("---")
    st.subheader("🎉 Step 3: Final Output Results")
    st.write("The server has completed your request:")
    
    saved_action = st.session_state.chosen_action
    
    # Execute the logic based on the saved choice
    if saved_action == "Count Words":
        word_count = len(user_text.split())
        st.metric(label="Total Word Count", value=word_count)
        
    elif saved_action == "Convert to UPPERCASE":
        st.info(f"**Uppercase Result:** {user_text.upper()}")
        
    elif saved_action == "Simulate AI Summary":
        st.warning(f"🤖 **Simulated AI Summary:** Your text contains {len(user_text)} characters and discusses '{user_text.split()[0]}...'")

    # Add a reset button to start over if they want
    if st.button("🔄 Start Over"):
        st.session_state.step_1_done = False
        st.session_state.step_2_done = False
        st.rerun()
