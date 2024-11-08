import streamlit as st
import os
import re
from PyPDF2 import PdfReader
import pandas as pd
import json
from openai import OpenAI
from datetime import datetime
import time  # Added for progress bar timing


# Ask for OpenAI API key
openai_api_key = st.text_input("Enter your OpenAI API key", type="password")
if not openai_api_key:
    st.warning("Please enter your OpenAI API key to proceed.")
    st.stop()
os.environ['OPENAI_API_KEY'] = openai_api_key

# Initialize Streamlit app
st.title("Batch PDF Data Extraction and Export")

# Step 1: Upload PDF files
uploaded_files = st.file_uploader("Upload PDF files", accept_multiple_files=True, type="pdf")

# Step 2: Input for fields to extract
fields_input = st.text_input(
    "Enter the fields you want to extract (comma-separated)",
    placeholder="e.g., address, postcode, energy_rating, energy_score, expiry_date"
)
st.write("Please enter fields separated by commas without spaces after commas.")

# Step 3: Start button to trigger processing
if st.button("Enter") and uploaded_files and fields_input:
    requested_fields = [field.strip() for field in fields_input.replace(' ','').split(',')]
    fields_str = "\n".join([f'- "{field}" <string>' for field in requested_fields])

    epc_texts = {}
    
    # Initialize progress bar
    progress_bar = st.progress(0)
    total_files = len(uploaded_files)
    step = 1 / total_files
    
    # Extract text from each uploaded PDF file
    for i, uploaded_file in enumerate(uploaded_files):
        file_name = uploaded_file.name
        reader = PdfReader(uploaded_file)
        txt = ''.join([page.extract_text() for page in reader.pages])
        epc_texts[file_name] = txt
        
        

    # Set up OpenAI API client
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

    # Create DataFrame for storing extracted data
    extracted_data = []
    for i, (file_name, text) in enumerate(epc_texts.items()):
        # Update progress
        progress_bar.progress((i + 1) * step, text=f"Processing {file_name}: {(i + 1)/len(epc_texts)*100:.2f}%")
        # Construct prompt with dynamically selected fields
        prompt = f"""
        You are a text processing agent working with lease agreement documents.

        Extract only specified values from the source text.
        Return answer as JSON object with the following fields:
        {fields_str}

        Use only the source text provided below.
        ========
        {text}
        ========
        """
        
        # Call OpenAI API to extract data
        response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="gpt-3.5-turbo-0125",
    )
        
        # Parse JSON response
        try:
            data = json.loads(response.choices[0].message.content)
            data['file_name'] = file_name
            extracted_data.append(data)
        except json.JSONDecodeError:
            st.error(f"Error parsing response for file {file_name}")

    # Convert extracted data into a DataFrame
    df = pd.DataFrame(extracted_data)
    df = df[['file_name'] + requested_fields]
    # Calculate success percentage if energy_rating is requested
    if 'energy_rating' in df.columns:
        success_percentage = (1 - df['energy_rating'].isna().mean()) * 100
    else:
        success_percentage = 0
    st.write(f"Success Percentage: {success_percentage:.2f}%")

    # Prepare for Excel download
    today_date = datetime.today().strftime('%d_%m_%y')
    excel_file = f'epc_data_{today_date}.xlsx'
    df.to_excel(excel_file, index=False)

    # Button for downloading the Excel file without re-running
    with open(excel_file, "rb") as file:
        st.download_button(
            label="Download Excel with Results",
            data=file,
            file_name=excel_file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

