> **Superseded.** This was the first sketch. The binding documents are now
> `.scratch/payment-visibility/spec.md` (what we are building), `/GLOSSARY.md`
> (the vocabulary), `docs/adr/` (the decisions) and `docs/adr/TECHNICAL-PLAN.md`
> (the file-by-file design). Kept for history; do not implement from this file.

What is this tool about? 
- To help manage payments
- Problem: A gym that does not track pending payments runs the risk of a member using the gym without pre-payment for the same. Given the high volume and non-structured movement of members and managers - it's difficult to track this payment. 
- Any service that has recurring problems runs this risk

Who is it for? 
- Anyone who provides a service
- V1: Aimed towards Gyms

How to use? 
- Plug Excel sheet with member information, subscription information and pending payments with date
- Our program 

Steps: 
- Read file
- Store file? 
- Go through file
- Check receivable from every member: 
    - If payment date < current date
        - if amount > 0
            member should be flagged
