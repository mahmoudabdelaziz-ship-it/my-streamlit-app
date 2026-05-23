import streamlit as st
import time

# Set up the page title and description
st.set_page_config(page_title="Interactive Test App", page_icon="⚙️")
st.title("Waiting for User Response Test")
st.write("This app will freeze at checkpoints and wait for your input before moving to the next block of code.")

st.markdown("---")

# 📥 CHECKPOINT 1: Wait for text input
st.subheader("Step 1: Provide the Input Data")
user_text = st.text_area("Type a paragraph or sentence here for the server to process:", 
                         placeholder="The quick brown fox jumps over the lazy dog...")

# This code block will ONLY run if the user has typed something in the text area
if user_text:
    st.success("✨ Checkpoint 1 Passed! The server received your text.")
    st.markdown("---")
    
    # 📥 CHECKPOINT 2: Wrapped in a form so the ENTER key works!
    st.subheader("Step 2: Choose an Action")
    st.write("Pick an option and press **Enter** (or click the button) to execute.")
    
    # Creating a form container
    with st.form(key="action_form"):
        action = st.selectbox("What should the server do with your text?", 
                              ["Count Words", "Convert to UPPERCASE", "Simulate AI Summary"])
        
        # Every form needs a submit button. Pressing 'Enter' while inside the dropdown triggers this button automatically.
        submit_button = st.form_submit_button(label="🚀 Execute Selected Action")
        
    # The code execution pauses here until the form is submitted (via Enter key or Click)
    if submit_button:
        st.write("### Output Results:")
        
        # Show a loading spinner to simulate processing time
        with st.spinner("Server is processing... please wait."):
            time.sleep(2) # Pauses for 2 seconds to show the server is working
            
        # Execute the logic based on the user's choice
        if action == "Count Words":
            word_count = len(user_text.split())
            st.metric(label="Total Word Count", value=word_count)
            
        elif action == "Convert to UPPERCASE":
            st.info(f"**Uppercase Result:** {user_text.upper()}")
            
        elif action == "Simulate AI Summary":
            st.warning(f"🤖 **Simulated AI Summary:** Your text contains {len(user_text)} characters and discusses '{user_text.split()[0]}...'")
            
        st.balloons() # Triggers a fun celebration animation on screen!
