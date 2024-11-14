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
        You are a text processing agent working with energy performance certificate documents.

        You are given the following:
        - Ratings with their score ranges: [A: 92+, B: 81-91, C: 69-80, D: 55-68, E: 39-54, F: 21-38, G: 1-20]
        - In the source text you may find the current rating in the format e.g. "49 E" and the potential rating in the format e.g. "C 70".

        Extract only specified values from the source text.
        Return answer as JSON object with the following fields:
        {fields_str}

        Keep in mind that if ratings and scores are requested above, you should only extract one letter for the energy_rating and potential_energy_rating fields and the energy_score and potential_energy_score fields should be an integer.

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
            try:
                data = json.loads(response.choices[0].message.content)
                data['file_name'] = file_name
                extracted_data.append(data)
            except json.JSONDecodeError:
                st.error(f"Error parsing response for file {file_name}")

    # Convert extracted data into a DataFrame
    df = pd.DataFrame(extracted_data)
    df = df[['file_name'] + requested_fields]
    if 'energy_score' in df.columns and 'potential_energy_score' in df.columns:
        mask = df['energy_score'] > df['potential_energy_score']
        
        # Store the original energy_score values temporarily
        temp_energy_scores = df.loc[mask, 'energy_score']
        
        # Update energy_score to match potential_energy_score where the condition is met
        df.loc[mask, 'energy_score'] = df.loc[mask, 'potential_energy_score']
        
        # Update potential_energy_score to the original energy_score values stored in temp_energy_scores
        df.loc[mask, 'potential_energy_score'] = temp_energy_scores

    # Calculate success percentage if energy_rating is requested
    # if 'energy_rating' in df.columns:
    #     success_percentage = (1 - df.isna().mean().mean()) * 100
    # else:
    #     success_percentage = 0

    st.write(f"Extracted data from {len(df)/len(epc_texts.items())*100:.2f}% of the documents.")
    

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
