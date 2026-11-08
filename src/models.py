from datetime import datetime
from dataclasses import dataclass

@dataclass
class Member: 
    name: str
    membership_amount: float
    join_date: str
    paid_amount: float
    installments: bool
    pending_amount: float
    next_payment_date: str
    number_of_installements: int = 2
    
    