import streamlit as st
import nltk
from nltk.tokenize import sent_tokenize
import io
import tempfile
import re
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
import pdfplumber
from collections import OrderedDict
from PyPDF2 import PdfReader, PdfWriter


# Download required NLTK data
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')

def improve_section_extraction(text):
    """Enhanced section extraction with better header detection and string handling"""
    lines = text.split('\n')
    sections = OrderedDict()
    current_section = None
    current_subsection = None
    current_content = []

    # Header pattern matching for section detection
    header_patterns = [
        r'^#+\s+(.+)$',  # Markdown headers
        r'^([A-Z][A-Za-z\s]+:)$',  # Title case with colon
        r'^(\d+\.(?:\d+\.)*)\s+([A-Z][A-Za-z\s]+)',  # Numbered sections
        r'^([A-Z][A-Z\s]{3,})$'  # All caps headers
    ]

    for line in lines:
        is_header = False
        for pattern in header_patterns:
            if re.match(pattern, line.strip()):
                is_header = True
                # Store previous content before switching to a new header
                if current_section:
                    if current_subsection:
                        # Ensure sections[current_section] is an OrderedDict
                        if not isinstance(sections.get(current_section), OrderedDict):
                            sections[current_section] = OrderedDict()
                        sections[current_section][current_subsection] = '\n'.join(current_content).strip()
                    else:
                        sections[current_section] = '\n'.join(current_content).strip()

                 # Set the new header and apply capitalization
                header_text = line.strip().lstrip('#').strip().title()
                if re.match(r'^\d+\.\d+', header_text):  # Subsection
                    current_subsection = header_text
                else:
                    current_section = header_text
                    current_subsection = None
                current_content = []
                break

        if not is_header and (current_section or current_subsection):
            current_content.append(line)


    # Add final section content if any
    if current_section:
        if current_subsection:
            if not isinstance(sections.get(current_section), OrderedDict):
                sections[current_section] = OrderedDict()
            sections[current_section][current_subsection] = '\n'.join(current_content).strip()
        else:
            sections[current_section] = '\n'.join(current_content).strip()

    return sections

def is_table_of_contents_page(text):
    """Heuristically determine if a page is a Table of Contents."""
    toc_patterns = [
        r"^contents$",  # Matches a page with only "Contents"
        r"chapter\s+\d+",  # Matches lines with "Chapter 1", "Chapter 2", etc.
        r"\.\.+\s*\d+$"  # Matches dots followed by page numbers
    ]
    
    lines = text.split('\n')
    match_count = sum(
        1 for line in lines
        if any(re.search(pattern, line.strip().lower()) for pattern in toc_patterns)
    )
    return match_count > 3  # Adjust threshold based on your document structure

def remove_toc_pages(uploaded_file):
    pdf_reader = PdfReader(uploaded_file)
    pdf_writer = PdfWriter()

    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and not is_table_of_contents_page(text):
                pdf_writer.add_page(pdf_reader.pages[i])

    # Save the modified PDF to a buffer
    buffer = io.BytesIO()
    pdf_writer.write(buffer)
    buffer.seek(0)
    return buffer

def extract_key_points(text, max_points=5):
    """Extract key points from text and ensure consistent single bullet formatting."""
    sentences = sent_tokenize(text)
    cleaned_sentences = []

    for sentence in sentences:
        # Remove any repeated bullet points and unnecessary symbols
        cleaned_sentence = re.sub(r'^\s*•+\s*', '• ', sentence).strip()  # Remove multiple leading bullets, but keep a single bullet
        cleaned_sentence = re.sub(r'^\s*[\-\*]+\s*', '• ', cleaned_sentence).strip()  # Remove leading bullet symbols, replace with single bullet
        cleaned_sentence = re.sub(r'\(\s*[a-zA-Z0-9]+\s*\)\s*', '', cleaned_sentence)  # Remove list markers like (a), (b), etc.
        cleaned_sentence = re.sub(r'^\d+\s*\.\s*', '• ', cleaned_sentence)  # Remove numbered list markers, replace with single bullet
        cleaned_sentence = re.sub(r'\s+', ' ', cleaned_sentence)  # Remove extra spaces

        # Add a single bullet point if the sentence is not empty
        if cleaned_sentence:
            cleaned_sentences.append(cleaned_sentence)

    # Return only the top `max_points` key points
    return cleaned_sentences[:max_points]
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, Table, TableStyle

def create_structured_pdf_summary(sections, metrics):
    """Creates a structured PDF summary based on a defined pattern."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()

    # Define custom styles
    styles.add(ParagraphStyle(
        'MainTitle', parent=styles['Heading1'], fontSize=24, spaceAfter=30, textColor=colors.HexColor('#2C3E50'), alignment=1
    ))
    styles.add(ParagraphStyle(
        'SectionTitle', parent=styles['Heading2'], fontSize=16, spaceBefore=20, spaceAfter=12, textColor=colors.HexColor('#34495E')
    ))

    styles.add(ParagraphStyle(
        'BulletPoint', parent=styles['Normal'], leftIndent=20, bulletIndent=10, spaceBefore=6, spaceAfter=6
    ))


    content = [Paragraph("Document Summary", styles['MainTitle']), Spacer(1, 20)]

    metrics_data = [
        ['Metric', 'Value'],
        ['Original Length', f"{metrics['original_words']} words"],
        ['Summary Length', f"{metrics['summary_words']} words"],
        ['Reduction', f"{metrics['reduction']}%"]
    ]
    metrics_table = Table(metrics_data, colWidths=[200, 200])
    metrics_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    content.append(metrics_table)
    content.append(Spacer(1, 30))

    for section_title, section_content in sections.items():
        content.append(Paragraph(section_title, styles['SectionTitle']))

        if isinstance(section_content, OrderedDict):
            for subsection_title, subsection_content in section_content.items():
                content.append(Paragraph(subsection_title, styles['Heading3']))
                key_points = extract_key_points(subsection_content)
                bullet_list = [ListItem(Paragraph(point, styles['Normal'])) for point in key_points]
                content.append(ListFlowable(bullet_list, bulletType='bullet', leftIndent=20))
        else:
            key_points = extract_key_points(section_content)
            bullet_list = [ListItem(Paragraph(point, styles['Normal'])) for point in key_points]
            content.append(ListFlowable(bullet_list, bulletType='bullet', leftIndent=20))

        content.append(Spacer(1, 12))

    doc.build(content)
    buffer.seek(0)
    return buffer

def main():
    st.title("📄 Enhanced Document Summarizer")

    st.markdown("""
    Upload your PDF document to get a structured summary with intelligent key point extraction.
    Optimized for regulatory and technical documents.
    """)

    reduction_ratio = st.slider(
        "Summary Length (% of original)",
        min_value=10,
        max_value=50,
        value=30,
        step=5
    )

    uploaded_file = st.file_uploader("Choose your PDF file", type="pdf")

    if uploaded_file is not None:
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()

            status_text.text("Extracting text from PDF...")
            progress_bar.progress(25)

            modified_pdf = remove_toc_pages(uploaded_file)

            with pdfplumber.open(modified_pdf) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() + "\n"

            progress_bar.progress(50)
            status_text.text("Analyzing document structure...")

            sections = improve_section_extraction(text)

            progress_bar.progress(75)
            status_text.text("Generating summary...")

            original_words = len(text.split())
            summary_words = sum(
                len(content.split()) if isinstance(content, str)
                else sum(len(subcontent.split()) for subcontent in content.values())
                for content in sections.values()
            )
            reduction_percentage = round((1 - summary_words/original_words) * 100, 1)

            metrics = {
                'original_words': original_words,
                'summary_words': summary_words,
                'reduction': reduction_percentage
            }

            tab1, tab2 = st.tabs(["Structured Summary", "Original Text"])

            with tab1:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Original Words", original_words)
                with col2:
                    st.metric("Summary Words", summary_words)
                with col3:
                    st.metric("Reduction", f"{reduction_percentage}%")

                for section_title, section_content in sections.items():
                    st.subheader(section_title)
                    if isinstance(section_content, OrderedDict):
                        for subsection_title, subsection_content in section_content.items():
                            st.markdown(f"**{subsection_title}**")
                            key_points = extract_key_points(subsection_content)
                            for point in key_points:
                                st.markdown(f"• {point}")
                    else:
                        key_points = extract_key_points(section_content)
                        for point in key_points:
                            st.markdown(f"• {point}")

            with tab2:
                st.subheader("Full Text")
                st.write(text)

            summary_pdf = create_structured_pdf_summary(sections, metrics)
            st.download_button(
                label="Download PDF Summary",
                data=summary_pdf,
                file_name="summary.pdf",
                mime="application/pdf"
            )

            progress_bar.progress(100)
            status_text.text("Summary ready!")

        except Exception as e:
            st.error(f"An error occurred: {e}")
            print(f"Error: {e}")
            import traceback
            print(traceback.format_exc())

if __name__ == "__main__":
    main()
