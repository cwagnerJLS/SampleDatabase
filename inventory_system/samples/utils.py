import pandas as pd

def read_excel_data(file_path):
    df = pd.read_excel(file_path)
    return df.to_dict('records')

def get_unique_values(data, key):
    return list({record[key] for record in data})

# Example usage
file_path = r"C:\Users\cwagner\PycharmProjects\Sample_Database\Sample Inventory.xlsx"
excel_data = read_excel_data(file_path)
unique_customers = get_unique_values(excel_data, 'Customer')
