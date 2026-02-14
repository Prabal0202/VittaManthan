# Screenshots Directory

This directory contains the UI screenshots referenced in the main README.md file.

## Required Screenshots

Please place the following screenshots in this directory:

### 1. `dashboard.png`
**Dashboard — Consolidated Financial Overview**

This screenshot should show:
- "All Accounts (Consolidated)" dropdown selector
- Summary cards displaying:
  - Total Income ₹4,343,689.79 (↗12%)
  - Total Spending ₹4,637,619.84 (↗8%)
  - Top Category "Others"
- Money Flow time-series chart showing Income vs Expenses (bar chart)
- Linked Accounts card displaying active consent information
- Spend Analysis donut chart (Others, UPI Payments, Card Spend, Cash Withdrawal)
- Highest Transactions table with transaction details
- Payment Modes bar chart (Others, UPI, Card, Cash)

### 2. `transactions.png`
**Transactions — Detailed Transaction History**

This screenshot should show:
- Horizontal scrolling Active Consent cards at the top of the page
- Detailed transaction table with columns:
  - Transaction ID
  - Account Number
  - Total (with ₹ amounts in green for credit/red for debit)
  - Type (Credit/Debit badges)
  - Date
  - Payment (Success status badges)
  - Payment Method (FT/CASH/UPI/OTHERS)
  - Reference Number
- Export buttons for PDF, Excel, CSV at top right of table
- Sidebar navigation with Transactions page selected

### 3. `consent-management.png`
**Consent Management — AA Consent Lifecycle**

This screenshot should show:
- Grid of consent cards styled like credit cards
- Each card displaying:
  - Consent ID (e.g., "TEST CONS ENTI D000")
  - Authorized User (e.g., "TEST22")
  - Consent Name
  - Status badge (ACTIVE green, PENDING yellow, REVOKED red, UNKNOWN gray)
- "Session Active (1:05)" countdown timer at the top
- "+ New Consent" button
- Sidebar navigation with Consent page selected

### 4. `ai-assistant.png`
**AI Assistant Chat — RAG-Powered Financial Intelligence**

This screenshot should show:
- User query: "Scan my recent transactions for any unusual or high-value activities. Explain the findings in English."
- AI response with:
  - "VECTOR SEARCH - Found 50 matches" badge
  - "TRANSACTION ANALYSIS SUMMARY" heading
  - Detailed table showing:
    - Date
    - Account Number
    - Amount (₹48,614.80 etc.)
    - Description
    - Transaction Type (CREDIT/DEBIT)
- "Select Active Consent" dropdown
- "Ingest Data" and "Clear History" buttons at the bottom
- Sidebar navigation with AI Assistant page selected

## Usage

After placing the screenshots in this directory, they will be automatically referenced in the main README.md using relative paths:

```markdown
<img src="docs/screenshots/dashboard.png" alt="VittaManthan Dashboard" width="100%"/>
```

## Image Guidelines

- **Format**: PNG format preferred (JPEG acceptable)
- **Resolution**: Minimum 1920x1080 for desktop screenshots
- **Quality**: High quality with clear text and UI elements
- **File Size**: Optimize for web (aim for < 2MB per image)
- **Content**: Ensure no sensitive or real user data is visible
