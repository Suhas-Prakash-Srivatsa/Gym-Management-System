# Gym payments

Payment tracking for gym managers, built on the members sheet you already keep.

## The problem

Most gyms keep their members in a spreadsheet: who joined, on which plan, for how much, and what they have paid. To find out who needs to pay, the manager has to go down that sheet row by row, work out each member's balance, and remember who has been owing for too long. It is slow, and it is easy to miss someone.

## What this tool does

You give it that same sheet, and it tells you:

- **who owes money**, and how much each one owes,
- **how much is owed in total**, and
- **who is overdue**, most overdue first, marked in red.

When a member pays, or a new member joins, you enter it on the dashboard and the figures update straight away. Your own sheet is never changed.

It was built quickly with [Claude Code](https://claude.com/claude-code), an AI coding assistant, working the way a small team would: a written spec, then small tickets, each one built test-first and checked by separate acceptance tests. The spec and tickets are kept in `.scratch/`.

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

## Try it with dummy data

No sheet to hand? On the upload screen, press **Skip to dashboard with dummy data**. The dashboard opens on a made-up gym, with a **Demo data** banner at the top.

- Everything works as it does with your own sheet: you can record payments and add members.
- The figures are worked out from the made-up sheet, exactly as they would be from yours. Its dates move with today's date, so there is always a mix of members who are paid up, owing and overdue.
- The demo is kept in its own folder, `data/Demo/`. It never touches your sheets, and it is not listed among your uploads.
- Each time you open the demo from the upload screen, it starts afresh. To start afresh without leaving, press **Reset demo data**.

Press **Open a different sheet** to go back to the upload screen.

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

**Not sure your sheet fits?** On the upload screen, open **View sample sheet**. It lists every column, says which are required, and shows a small example. Press **Download sample sheet (CSV)** to get that example as a file. You can open it in Excel, fill in your own members, and upload it. Uploaded as it is, it opens straight on the dashboard with nothing to fix.

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

The tool only ever reads your sheet. It never writes to it. Everything you do on the dashboard is saved in files next to its copy of your sheet, so it is still there the next time you open it:

- **`payments.csv`** holds the payments you record in the tool, including money paid when you add a new member. New payments are added at the end. Nothing in it is ever changed or deleted.
- **`members_clean.csv`** holds your sheet with the corrections you made on screen and the members you added. When it exists, the tool uses it instead of the sheet, and tells you so.
- **`members_clean.csv.<date-time>.bak`** is an old set of corrections you chose to discard, together with any memberships that were not in your sheet (including members you added on screen). It is moved aside, never deleted. Payments for those memberships stay in `payments.csv`; the dashboard lists them as warnings and does not count them until the memberships are back in the sheet.

You can open these files in Excel to look at them. Please do not edit them by hand, and close them again before you record anything: while Excel has a file open, the tool cannot save to it and tells you so.

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

## Adding a member

Under **Record a payment** is **Add a new member**.

1. Type the **Member name**.
2. Choose the **Membership type**: Monthly, Half-Yearly or Yearly.
3. Check the **Date joined**. It starts at today.
4. Type the **Membership amount**, the full price for the whole period, and the number of **Installments**.
5. If the member paid something when joining, type it under **Paid at sign-up** and check its date. Otherwise leave it empty.
6. Press **Add member**.

The new member appears in the table, the totals and the **Member** list of Record a payment straight away. The tool gives them a new Member ID and Membership ID in the style your sheet already uses (for example `M025` and `MS-027`), never one that is already taken.

**Starting a new gym:** a sheet with only the column names (download the sample sheet and delete its rows) opens an empty dashboard. Add your first member there.

**Where it is saved:** the member is added to `members_clean.csv`, and money paid at sign-up is saved in `payments.csv` like any other payment. Your own sheet is not changed, so if you want the member in it too, add them there yourself.

The tool refuses an empty name, an amount that is not money, installments below 1, or more paid than the membership costs. It also refuses a name that is already in your sheet on a row with no Member ID, because it could not tell the two people apart: give that member an ID in your sheet first, or add an initial to the new name. It warns you, but still lets you add, if a date is in the future, if the money was paid before the date joined, or if another member already has that name (it then adds a second, different person).

**Please note:** if you later upload a changed copy of your sheet, the tool asks whether to keep your corrections. It also tells you how many memberships in your corrections are not in your sheet (including members added here) and names them. Choosing **Discard** sets those aside too (into the `.bak` file), and any payments recorded for them then show as warnings and are not counted. So add them to your sheet first.

A name can be at most 100 characters and cannot start with `=`, `+`, `-` or `@` (Excel would treat it as a formula). The membership amount can be at most ₹1,00,00,000 and installments at most 120, to catch a slipped finger. You must choose the membership type yourself; there is no default.

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

`tests/test_golden.py` loads `src/files/Book1.csv` on 8 November 2026 and checks the figures worked out by hand: 19 memberships owing money, 11 of them overdue, ₹97,300 receivable and ₹60,950 overdue. `tests/test_demo.py` does the same for the demo gym (`src/files/demo_members.csv`): ₹70,500 receivable and ₹29,500 overdue on that day.

## What this version does not do

- **No accounts or logins.** It is for one owner on one computer.
- **No hosting.** It runs on your computer only, not on the internet.
- **No overpayment.** A payment cannot be more than what is still owed. There is no credit or advance balance.
- **One demo at a time.** The demo uses one folder on your computer. If two browser tabs both open the demo, they share it, and resetting it in one tab resets it for the other.
- **Comma-separated CSV only.** Some versions of Excel save CSV files with semicolons (`;`) between the columns. The tool cannot read those; save the sheet as "CSV UTF-8 (comma delimited)" or as `.xlsx` instead.
