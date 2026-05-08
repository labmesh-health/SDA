# SDA
A Streamlit web app that automates the formatting and unpivoting of raw diagnostic instrument CSV exports into clean, long-format data
# 💡 converterPRO

**converterPRO** is a Python and Streamlit web application designed to clean, format, and unpivot raw CSV data exported from diagnostic laboratory instruments (e.g., Roche systems). 

Originally built as a Google Apps Script workflow, this upgraded Python version processes data instantly in-memory, ensuring speed, reliability, and strict data privacy.

## ✨ Features
* **Automated Data Unpivoting:** Dynamically detects repeating test blocks (8-column or 11-column formats) and unpivots them from a wide-format export into a clean, long-format dataset.
* **Intelligent Mapping:** Automatically translates instrument numeric codes into human-readable text (e.g., Discrimination `1` becomes `Routine`, Sample_Type `1` becomes `Serum/Plasma`).
* **Instant Export:** One-click download of the processed dataset.
* **Privacy First:** Data processing happens entirely in-memory on your local machine or server. No sensitive instrument or patient data is stored or transmitted.

## 🛠️ Prerequisites
* Python 3.8 or higher installed on your machine.

## 🚀 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR-USERNAME/converterPRO.git](https://github.com/YOUR-USERNAME/converterPRO.git)
   cd converterPRO
