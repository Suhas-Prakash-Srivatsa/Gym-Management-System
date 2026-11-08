import csv
from models import Member

DEFAULT_PATH = "files/Book1.csv"

def get_csv_data(filepath=DEFAULT_PATH, hasHeader: bool = True):
    data = []
    with open(filepath, 'r') as csv_file: 
        reader = csv.DictReader(csv_file) #Returns an object

    #     for line_no, row in enumerate(reader, start=2):
    #           data.append(
    #                Member(
    #                     name: row["name"].strip()
    #                     membership_amount: row['membership_amount']
    #                     join_date: datetime
    #                     paid_amount: float
    #                     installments: bool
    #                     pending_amount: float
    #                     next_payment_date: datetime
    #                     number_of_installements: int = 2
    #                )
    #                )

    # return data

Data = get_csv_data()
print(Data)