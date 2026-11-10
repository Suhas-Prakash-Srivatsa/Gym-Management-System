# Gym Management System

A small tool for a gym owner to help manage receivables from members. Owners can simply feed their sheet with information related to members, membership and payments. It shows you who still owes money, how much in total, and who is late. You can also record a payment when a member pays.

## What it answers

- **How much money is still owed to me?** This is the **Total Receivable**.
- **How much of that is late?** This is the **Overdue** figure.
- **Who owes, and who is late?** A table lists every membership that still owes money. The most overdue are at the top. A late one has a red **DUE** tag.

It also shows the number of members and the total value of all memberships.

## Install and run

You need Python 3.14 on your computer.

1. Open a terminal in this folder.
2. Install what the tool needs (once):

   ```
   pip install -r requirements.txt
   ```

3. Start the tool:

   ```
   streamlit run app.py
   ```

Your web browser opens on the tool. It runs only on your own computer.

## Opening your sheet

The tool opens on the **upload screen**. This is the normal way in.

1. Click to choose your members sheet. It can be a CSV file (`.csv`) or an Excel file (`.xlsx`).
2. The dashboard opens. If something in the sheet cannot be read, you see a list of the problems instead (see **Fixing problems in the sheet** below).

The tool keeps its own copy of your sheet in the `data` folder, next to `app.py`. Each sheet gets its own folder there, for example `data/Book1_csv/Book1.csv`. Your payments and corrections are saved in that folder too.

**Coming back later:** the upload screen also lists your earlier uploads, the most recently used first. Pick one and press **Open**. Your payments and corrections are still there. You do not need to upload again.

**Uploading the same sheet again:** if you upload a sheet with the same name, the tool uses the same folder. Payments you already recorded are kept, and the tool tells you so. Letter case does not matter: `Book1.csv` and `book1.csv` count as the same sheet.

To switch sheets, press **Open a different sheet** on the dashboard.

## What your sheet must have

The first row of the sheet holds the column names. The tool understands several names for each column. Case does not matter, and `_` or `-` count as spaces.

**Required columns:**

| Column | Names the tool accepts |
|---|---|
| Member Name | Member Name, Name, Member |
| Membership Type | Membership Type, Type, Plan |
| Date Joined | Date Joined, Joined, Join Date, Joining Date |
| Membership Amount | Membership Amount, Amount, Contract Amount |
| Installments | Installments, Instalments |
| Paid Amount | Paid Amount, Paid, Amount Paid |

**Optional columns:**

| Column | Names the tool accepts |
|---|---|
| Member ID | Member ID, ID |
| Membership ID | Membership ID |
| Last Payment Date | Last Payment Date, Last Paid, Date of Payment |

What goes in them:

- **Membership Type** is Monthly, Half-Yearly or Yearly.
- **Membership Amount** is the full price for the whole period. For a yearly membership, it is the price of all twelve months. Write it as `12000`, `12,000` or `₹12,000`.
- **Installments** is how many payments the price is split into. `1` means paid in one go.
- **Paid Amount** is what the member has paid so far. Write `0` if nothing yet.
- **Last Payment Date** is needed on any row where something was paid.
- **Dates** can be written as `2026-06-01`, `01/06/2026` or `1 June 2026`. Always include the year, with four digits.
- A member who renewed has one row per membership. Rows with the same **Member ID** are the same person.
- If a name appears on more than one row, and not every one of those rows has a Member ID, the tool asks you whether it is one person or two.

Other columns are ignored.

## Your sheet is never changed

The tool only ever reads your sheet. It never writes to it. Everything it saves goes into files next to its copy of your sheet:

- **`payments.csv`** holds the payments you record in the tool. New payments are added at the end. Nothing in it is ever changed or deleted.
- **`members_clean.csv`** holds your sheet with the corrections you made on screen. When it exists, the tool uses it, and tells you so.
- **`members_clean.csv.<date-time>.bak`** is an old set of corrections you chose to discard. It is moved aside, never deleted.

Please do not edit these files by hand.

## Fixing problems in the sheet

If something in the sheet cannot be read, the tool shows no figures. A dashboard built on half-read rows would show wrong totals. Instead it lists each problem, with its row and column.

Most problems can be fixed on screen:

- A date without a year: choose **Use this year**, or type the date.
- A paid amount with no payment date: choose **Use the Date Joined**, or type the date.
- Two rows with the same name: say whether it is **the same person** (a renewal) or **different people** who share a name.
- A wrong type, amount or number: type the correct value.

Then press **Apply fixes**. Your answers are saved in `members_clean.csv`. Your sheet stays as it was.

A missing column, or the same column given twice, must be fixed in the sheet itself. Fix it, save the sheet and upload it again.

If you later change the sheet and upload it again, the tool asks whether to keep your earlier corrections or discard them.

## Recording a payment

Under the table is **Record a payment**.

1. Choose the **Member**.
2. If that member has more than one membership, a **Membership** box appears. It picks the one due soonest that still owes money. Change it if the payment is for another one. A member with only one membership gets no box; the payment goes to that membership.
3. Type the **Amount**, for example `6000` or `₹6,000`.
4. Check the **Paid on** date. It starts at today.
5. Press **Record payment**.

The figures update straight away. The tool refuses a payment larger than what is still owed, and tells you the most you can enter. It warns you, but still lets you record, if the date is in the future or before the member joined.

## When is a payment late?

Every membership gets a fixed grace period of **two calendar months**:

- after the last payment, or
- after the date joined, if nothing has been paid yet.

The day after that, if money is still owed, the membership is **Overdue** and shows **DUE**. A fully paid membership is never overdue.

Example: Rohit joined on 5 September and has paid nothing. He is not late on 5 November. He is late from 6 November.

**Please note:** any payment, even a small one, starts a new two months. A ₹100 payment takes the whole amount still owed off the Overdue figure for two months. Whether this is the right rule is still being decided.

## For developers

You can skip the upload screen and open a sheet directly:

```
streamlit run app.py -- path/to/sheet.csv
```

Or set environment variables:

| Variable | What it does |
|---|---|
| `GYM_SHEET` | Opens this sheet directly, like the path above. Its sidecar files go next to it. |
| `GYM_DATA_DIR` | Keeps upload copies in this folder instead of `./data`. |
| `GYM_TODAY` | Fixes today's date, for example `2026-11-08`. For tests and demos. |

The design is in `.scratch/payment-visibility/` (`spec.md`, `TECHNICAL-PLAN.md`), with the words used in `GLOSSARY.md` and the decisions in `docs/adr/`.

## Running the tests

```
python -m pytest -q
```

`tests/test_golden.py` loads `src/files/Book1.csv` on 8 November 2026 and checks the figures worked out by hand: 19 memberships owing money, 11 of them overdue, ₹97,300 receivable and ₹60,950 overdue.

## What this version does not do

- **No accounts or logins.** It is for one owner on one computer.
- **No hosting.** It runs on your computer only, not on the internet.
- **No overpayment.** A payment cannot be more than what is still owed. There is no credit or advance balance.
