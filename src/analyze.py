from loader import get_csv_data

file = get_csv_data()

for data in file: 
    paid_amount = int(data[4])
    membership_amount = int(data[2])
    installments = True
    pending_amount = 0

    print(f"""
        The Total Amount due is {membership_amount}.
        {data[0]} has paid {paid_amount}. 
                """)
    
    if paid_amount < membership_amount: 
        pending_amount = membership_amount - paid_amount
        if installments == True: 
            no_of_installments = data[3]
            pending_amount /= installments
            print(f"{data[0]} owes {pending_amount} in {installments} installments") 